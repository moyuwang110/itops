"""运维工具箱：地址扫描与 DHCP 信息查询。

安全约束：
- 仅允许扫描私有 IP 段（RFC 1918），避免被用作外网探测跳板；
- 单次扫描最多 256 个地址（/24），防止资源耗尽；
- 每个地址探测有超时上限，并发数受控。
"""
from __future__ import annotations

import asyncio
import csv
import io
import ipaddress
import json
import logging
import os
import re
import socket
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from app.core.config import settings

logger = logging.getLogger(__name__)

# 允许扫描的私网网段（RFC 1918 + 环回 + 链路本地）
_PRIVATE_NETWORKS = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),
]

# 单次扫描最大地址数
MAX_SCAN_HOSTS = 256
# 单主机 ping 超时（秒）
PING_TIMEOUT = 1.0
# TCP 连接超时（秒）
TCP_TIMEOUT = 0.8
# 并发探测数
SCAN_CONCURRENCY = 32
# 常用 TCP 端口：用于在 ICMP 被禁时仍能探测主机存活
DEFAULT_TCP_PORTS = [80, 443, 22, 3389, 445, 8080]


def _is_private_cidr(cidr: str) -> ipaddress.IPv4Network | ipaddress.IPv6Network:
    """校验 CIDR 合法性且属于私网，返回 network 对象；否则抛 ValueError。"""
    try:
        net = ipaddress.ip_network(cidr, strict=False)
    except ValueError as exc:
        raise ValueError(f"无效的 CIDR 地址：{cidr}") from exc
    if net.version != 4:
        raise ValueError("仅支持 IPv4 地址扫描")
    for priv in _PRIVATE_NETWORKS:
        if net.subnet_of(priv):
            if net.num_addresses > MAX_SCAN_HOSTS:
                raise ValueError(f"扫描范围过大，最多支持 {MAX_SCAN_HOSTS} 个地址（/24）")
            return net
    raise ValueError("仅允许扫描私有 IP 段（10.x / 172.16-31.x / 192.168.x）")


async def _ping_host(ip: str) -> tuple[bool, float | None]:
    """使用系统 ping 探测主机是否存活，返回 (是否存活, 响应毫秒数)。"""
    try:
        proc = await asyncio.create_subprocess_exec(
            "ping", "-c", "1", "-W", str(int(PING_TIMEOUT)), ip,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        stdout, _ = await proc.communicate()
        if proc.returncode != 0:
            return False, None
        # 解析 ping 输出中的 time=X ms
        m = re.search(rb"time=([\d.]+)\s*ms", stdout)
        ms = float(m.group(1)) if m else None
        return True, ms
    except (FileNotFoundError, OSError, ValueError):
        return False, None


async def _tcp_probe(ip: str, port: int) -> tuple[bool, float]:
    """尝试 TCP 连接指定端口，返回 (是否连通, 响应毫秒数)。"""
    start = datetime.now()
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(ip, port), timeout=TCP_TIMEOUT
        )
        writer.close()
        await writer.wait_closed()
        elapsed = (datetime.now() - start).total_seconds() * 1000
        return True, round(elapsed, 1)
    except (asyncio.TimeoutError, OSError, ConnectionRefusedError):
        return False, 0.0


async def _probe_host(ip: str) -> dict:
    """综合探测主机：ping + TCP 多端口探测。

    存活主机返回 open_ports（开放端口列表）和 response_ms（响应毫秒数），
    以便前端 tooltip 展示端口开放情况与响应延迟。
    """
    # 1) ping 探测
    ping_ok, ping_ms = await _ping_host(ip)

    # 2) 无论 ping 是否成功，都尝试 TCP 常用端口（收集开放端口）
    open_ports: list[int] = []
    tcp_response_ms: float | None = None
    for port in DEFAULT_TCP_PORTS:
        ok, ms = await _tcp_probe(ip, port)
        if ok:
            open_ports.append(port)
            if tcp_response_ms is None:
                tcp_response_ms = ms

    if ping_ok or open_ports:
        # 优先使用 ping 的响应时间，回退到 TCP 响应时间
        response_ms = ping_ms if ping_ms is not None else tcp_response_ms
        source = "icmp" if ping_ok else f"tcp/{open_ports[0]}"
        return {
            "alive": True,
            "source": source,
            "response_ms": response_ms,
            "open_ports": sorted(open_ports),
        }
    return {"alive": False, "source": "", "response_ms": None, "open_ports": []}


def _resolve_hostname(ip: str) -> str:
    """反向解析主机名，失败返回空串。"""
    try:
        return socket.gethostbyaddr(ip)[0]
    except (socket.herror, socket.gaierror, OSError):
        return ""


def _read_arp_table() -> dict[str, str]:
    """读取 /proc/net/arp，返回 ip -> mac 映射。"""
    table: dict[str, str] = {}
    try:
        with open("/proc/net/arp", "r", encoding="utf-8") as f:
            next(f, None)  # 跳过表头
            for line in f:
                parts = line.split()
                if len(parts) >= 4:
                    ip, _, _, mac = parts[0], parts[1], parts[2], parts[3]
                    if mac != "00:00:00:00:00:00":
                        table[ip] = mac
    except OSError:
        pass
    return table


async def scan_addresses(cidr: str) -> dict:
    """扫描指定私网 CIDR，返回全部地址的状态网格与统计。

    地址状态：used（已用/存活）、free（空闲）、unknown（未知）、conflict（冲突）
    返回结构：{"cidr", "gateway", "netmask", "total", "used", "free", "unknown",
              "conflict", "utilization", "last_scan", "addresses": [...]}
    """
    net = _is_private_cidr(cidr)
    all_ips = [str(h) for h in net.hosts()]
    if not all_ips:
        return {"cidr": cidr, "gateway": "", "netmask": str(net.netmask),
                "total": 0, "used": 0, "free": 0, "unknown": 0,
                "conflict": 0, "utilization": 0.0, "last_scan": "", "addresses": []}

    # 网关约定为网段第一个主机地址
    gateway = all_ips[0]
    scanned_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    logger.info("开始地址扫描：%s（%d 个地址）", cidr, len(all_ips))

    sem = asyncio.Semaphore(SCAN_CONCURRENCY)

    async def _probe(ip: str) -> tuple[str, dict]:
        async with sem:
            return ip, await _probe_host(ip)

    results = await asyncio.gather(*[_probe(ip) for ip in all_ips])
    probe_map: dict[str, dict] = dict(results)

    # 扫描后从 ARP 表补充 MAC
    arp = _read_arp_table()

    addresses: list[dict] = []
    for ip in all_ips:
        probe = probe_map[ip]
        mac = arp.get(ip, "")
        hostname = _resolve_hostname(ip) if probe["alive"] else ""
        addresses.append({
            "ip": ip,
            "status": "used" if probe["alive"] else "free",
            "mac": mac,
            "hostname": hostname,
            "response_ms": probe["response_ms"],
            "open_ports": probe["open_ports"],
            "source": probe["source"],
            "discovered_at": scanned_at if probe["alive"] else "",
            "note": "" if probe["alive"] else "no-response",
        })

    # 冲突检测：IP 对应多 MAC 或 MAC 对应多 IP 均标记为 conflict
    addresses = _detect_conflicts(addresses)

    total = len(addresses)
    used = sum(1 for a in addresses if a["status"] == "used")
    free = sum(1 for a in addresses if a["status"] == "free")
    unknown = sum(1 for a in addresses if a["status"] == "unknown")
    conflict = sum(1 for a in addresses if a["status"] == "conflict")
    utilization = round(used / total * 100, 1) if total else 0.0

    logger.info("地址扫描完成：%s，已用 %d/%d，利用率 %.1f%%", cidr, used, total, utilization)
    return {
        "cidr": cidr,
        "gateway": gateway,
        "netmask": str(net.netmask),
        "total": total,
        "used": used,
        "free": free,
        "unknown": unknown,
        "conflict": conflict,
        "utilization": utilization,
        "last_scan": scanned_at,
        "addresses": addresses,
    }


def _detect_conflicts(addresses: list[dict]) -> list[dict]:
    """双向冲突检测：
    - 同一 IP 对应多个 MAC（ARP 漂移）→ conflict
    - 同一 MAC 对应多个 IP → conflict
    """
    ip_to_macs: dict[str, set[str]] = {}
    mac_to_ips: dict[str, set[str]] = {}

    for a in addresses:
        if a["status"] != "used" or not a["mac"]:
            continue
        mac = a["mac"].lower()
        ip_to_macs.setdefault(a["ip"], set()).add(mac)
        mac_to_ips.setdefault(mac, set()).add(a["ip"])

    for a in addresses:
        if a["status"] != "used":
            continue
        macs = ip_to_macs.get(a["ip"])
        if macs and len(macs) > 1:
            a["status"] = "conflict"
            a["note"] = f"IP {a['ip']} 对应多个 MAC: {', '.join(sorted(macs))}"
            continue
        if a["mac"]:
            ips = mac_to_ips.get(a["mac"].lower())
            if ips and len(ips) > 1:
                a["status"] = "conflict"
                a["note"] = f"MAC {a['mac']} 出现在多个 IP: {', '.join(sorted(ips))}"
    return addresses


# ---------- DHCP 信息 ----------

# ISC dhcpd 租约块正则
_ISC_LEASE_RE = re.compile(
    r"lease\s+(?P<ip>[\d.]+)\s*\{(?P<body>.*?)\}",
    re.DOTALL,
)
# 按行匹配租约块内的字段：starts / ends / hardware / client-hostname / binding state
# 注意必须锚定行首，避免 "next binding state free" 覆盖 "binding state active"
_ISC_FIELD_RE = re.compile(
    r"^\s*(?P<key>starts|ends|hardware|client-hostname|binding)\s+(?P<value>[^;]+);",
    re.MULTILINE,
)

# 姓名映射存储路径
_NAMEMAP_PATH = Path(getattr(settings, "data_dir", "/app/data")) / "dhcp_namemap.json"
_NAMEMAP_PATH.parent.mkdir(parents=True, exist_ok=True)

# MAC 归一化正则
_MAC12_RE = re.compile(r"^[0-9a-f]{12}$")

# DHCP 地址状态分类
_STATE_LABELS = {
    "active": "Active",
    "inactive": "Inactive",
    "reserved": "Reserved",
    "declined": "Declined",
}


def _format_mac(client_id: str) -> str:
    """MAC 归一化为 0088-6536-1e4a 形式（小写，4-4-4 分组，连字符分隔）。

    兼容 00-88-65-36-1e-4a / 00:88:65:36:1e:4a / 0088.6536.1e4a / 008865361e4a 等写法；
    不是 12 位十六进制的（如 DUID 长串）原样返回。
    """
    raw = (client_id or "").strip()
    s = re.sub(r"[-:.\s]", "", raw).lower()
    if _MAC12_RE.match(s):
        return "-".join(s[i:i + 4] for i in (0, 4, 8))
    return raw


def _mac_canonical(s: str) -> str:
    """MAC 的比较形态：去分隔符、小写，如 008865361e4a。"""
    return re.sub(r"[-:.\s]", "", (s or "")).lower()


# ---------- 姓名映射 ----------


def _load_namemap() -> dict[str, str]:
    """加载姓名映射（主机名/IP/MAC -> 姓名）。"""
    if not _NAMEMAP_PATH.exists():
        return {}
    try:
        data = json.loads(_NAMEMAP_PATH.read_text(encoding="utf-8"))
        return {str(k): str(v) for k, v in data.items()} if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def _save_namemap(mapping: dict[str, str]) -> None:
    """原子写入姓名映射。"""
    tmp = _NAMEMAP_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(mapping, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, _NAMEMAP_PATH)


def _norm_key(s: str) -> str:
    return (s or "").strip().lower()


def _match_name(lease: dict, namemap: dict[str, str]) -> str:
    """按 主机名 -> IP -> MAC 顺序匹配姓名，两侧均做归一化对齐。"""
    hn = (lease.get("hostname") or "").strip()
    hn_candidates = [_norm_key(hn)] if hn else []
    if "." in hn:
        hn_candidates.append(_norm_key(hn.split(".")[0]))
    for c in hn_candidates:
        if c and c in namemap:
            return namemap[c]
    ip = _norm_key(lease.get("ip"))
    if ip and ip in namemap:
        return namemap[ip]
    mac = lease.get("mac") or ""
    cmac = _mac_canonical(mac)
    if len(cmac) == 12:
        if cmac in namemap:
            return namemap[cmac]
        for k, v in namemap.items():
            if _mac_canonical(k) == cmac:
                return v
    return ""


def list_namemap() -> list[dict]:
    """列出全部姓名映射。"""
    m = _load_namemap()
    return [{"key": k, "name": v} for k, v in sorted(m.items())]


def add_namemap(key: str, name: str) -> dict:
    """添加或更新姓名映射。"""
    k = _norm_key(key)
    name = (name or "").strip()
    if not k or not name:
        raise ValueError("key 与 name 不能为空")
    if len(k) > 128 or len(name) > 64:
        raise ValueError("key 或 name 过长")
    m = _load_namemap()
    m[k] = name
    _save_namemap(m)
    return {"status": "ok", "total": len(m)}


def delete_namemap(key: str) -> dict:
    """删除姓名映射。"""
    m = _load_namemap()
    k = _norm_key(key)
    if k not in m:
        raise ValueError("映射不存在")
    m.pop(k)
    _save_namemap(m)
    return {"status": "ok", "total": len(m)}


# ---------- DHCP 快照存储（Windows DHCP 服务器推送） ----------

_DHCP_DATA_DIR = Path(getattr(settings, "data_dir", "/app/data")) / "dhcp"
_DHCP_DATA_DIR.mkdir(parents=True, exist_ok=True)
_SAFE_ID = re.compile(r"^[\w\-. ]{1,64}$")
_HIST_DATE = re.compile(r"^(\d{8})_\d{6}\.json$")
# Windows DHCP 推送的原始字段
_UPLOAD_FIELDS = ("IPAddress", "ScopeId", "ClientId", "HostName", "AddressState", "LeaseExpiryTime")


def _server_dir(server_id: str) -> Path:
    if not _SAFE_ID.match(server_id or ""):
        raise ValueError("server 名称只允许字母/数字/_-/. 和空格，长度1-64")
    return _DHCP_DATA_DIR / server_id


def _purge_old_history(sdir: Path) -> int:
    """清理超过保留期的历史快照，返回删除数量。"""
    hist = sdir / "history"
    if not hist.exists():
        return 0
    cutoff = (datetime.now() - timedelta(days=getattr(settings, "dhcp_retention_days", 7))).strftime("%Y%m%d")
    removed = 0
    for p in hist.glob("*.json"):
        m = _HIST_DATE.match(p.name)
        if m and m.group(1) < cutoff:
            try:
                p.unlink()
                removed += 1
            except OSError:
                pass
    if removed:
        logger.info("清理 %s 过期历史 %d 个文件", sdir.name, removed)
    return removed


def _save_snapshot(server_id: str, payload: dict) -> None:
    """保存 latest.json，同时归档一份带时间戳的历史文件，并清理过期历史。"""
    sdir = _server_dir(server_id)
    hist_dir = sdir / "history"
    hist_dir.mkdir(parents=True, exist_ok=True)

    latest = sdir / "latest.json"
    tmp = sdir / ".latest.json.tmp"
    tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, latest)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    hist = hist_dir / f"{ts}.json"
    tmp2 = hist_dir / f".{ts}.json.tmp"
    tmp2.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp2, hist)

    _purge_old_history(sdir)


def _load_latest_snapshot(server_id: str) -> Optional[dict]:
    """读取某服务器的最新快照。"""
    path = _server_dir(server_id) / "latest.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        logger.error("读取 DHCP 快照失败 %s: %s", path, exc)
        return None


def list_dhcp_servers() -> list[dict]:
    """列出所有有数据的 DHCP 服务器。"""
    if not _DHCP_DATA_DIR.exists():
        return []
    out = []
    for sdir in sorted(_DHCP_DATA_DIR.iterdir()):
        if not sdir.is_dir() or sdir.name.startswith("."):
            continue
        latest = sdir / "latest.json"
        if not latest.exists():
            continue
        try:
            data = json.loads(latest.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        leases = data.get("leases") or []
        out.append({
            "id": sdir.name,
            "display_name": data.get("server") or sdir.name,
            "collected_at": data.get("collectedAt") or "",
            "received_at": data.get("receivedAt") or "",
            "count": len(leases),
        })
    return out


def receive_dhcp_upload(payload: dict, token: str) -> dict:
    """接收 Windows DHCP 服务器推送的租约数据并落盘。"""
    if token != getattr(settings, "dhcp_upload_token", ""):
        raise PermissionError("无效的上传令牌")
    server = str(payload.get("server") or "").strip()
    if not server:
        raise ValueError("缺少 server 字段")
    leases = payload.get("leases")
    if not isinstance(leases, list):
        raise ValueError("leases 必须是数组")

    cleaned = []
    for item in leases:
        if not isinstance(item, dict):
            continue
        cleaned.append({k: str(item.get(k) or "") for k in _UPLOAD_FIELDS})

    snapshot = {
        "server": server,
        "collectedAt": str(payload.get("collectedAt") or ""),
        "receivedAt": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "count": len(cleaned),
        "leases": cleaned,
    }
    _save_snapshot(server, snapshot)
    logger.info("接收 %s 租约 %d 条", server, len(cleaned))
    return {"status": "ok", "server": server, "count": len(cleaned)}


def _snapshot_to_leases(snap: dict) -> list[dict]:
    """将 Windows DHCP 快照（PascalCase 字段）转换为前端使用的小写字段格式。"""
    leases = snap.get("leases") or []
    out = []
    for item in leases:
        out.append({
            "ip": item.get("IPAddress", ""),
            "mac": item.get("ClientId", ""),
            "hostname": item.get("HostName", ""),
            "starts": "",
            "ends": item.get("LeaseExpiryTime", ""),
            "state": (item.get("AddressState", "") or "").lower(),
        })
    return out


# ---------- 租约解析 ----------


def _parse_isc_leases(content: str) -> list[dict]:
    """解析 ISC dhcpd 的 dhcpd.leases 格式。"""
    leases: list[dict] = []
    for m in _ISC_LEASE_RE.finditer(content):
        ip = m.group("ip")
        body = m.group("body")
        entry: dict = {"ip": ip, "mac": "", "hostname": "", "starts": "", "ends": "", "state": ""}
        for fm in _ISC_FIELD_RE.finditer(body):
            key = fm.group("key")
            val = fm.group("value").strip().strip('"')
            if key == "starts":
                entry["starts"] = val
            elif key == "ends":
                entry["ends"] = val
            elif key == "hardware":
                parts = val.split()
                if len(parts) >= 2:
                    entry["mac"] = parts[1]
            elif key == "client-hostname":
                entry["hostname"] = val
            elif key == "binding":
                # binding state active / free / abandoned
                parts = val.split()
                if len(parts) >= 2 and parts[0] == "state":
                    entry["state"] = parts[1]
        # ISC binding state 转换为通用状态
        if entry["state"] in ("active",):
            entry["state"] = "active"
        elif entry["state"] in ("free", "abandoned", "backup"):
            entry["state"] = "inactive"
        else:
            entry["state"] = "active" if entry["ends"] else ""
        leases.append(entry)
    return leases


def _parse_dnsmasq_leases(content: str) -> list[dict]:
    """解析 dnsmasq 的租约文件（每行：expiry mac ip hostname client-id）。"""
    leases: list[dict] = []
    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) < 4:
            continue
        expiry_ts = parts[0]
        try:
            ends = datetime.fromtimestamp(int(expiry_ts)).strftime("%Y-%m-%d %H:%M:%S")
        except (ValueError, OSError):
            ends = expiry_ts
        leases.append({
            "ip": parts[2],
            "mac": parts[1],
            "hostname": parts[3] if parts[3] != "*" else "",
            "starts": "",
            "ends": ends,
            "state": "active",
        })
    return leases


def _get_local_interfaces() -> list[dict]:
    """获取本机网卡 IP 信息（通过 ip addr 命令）。"""
    interfaces: list[dict] = []
    try:
        proc = subprocess.run(
            ["ip", "-4", "addr", "show"],
            capture_output=True, text=True, timeout=5,
        )
        if proc.returncode != 0:
            return interfaces
        current = None
        for line in proc.stdout.splitlines():
            line = line.strip()
            m = re.match(r"\d+:\s+(\S+):", line)
            if m:
                current = {"name": m.group(1), "ip": "", "mac": ""}
                em = re.search(r"link/ether\s+([0-9a-fA-F:]+)", line)
                if em:
                    current["mac"] = _format_mac(em.group(1))
                interfaces.append(current)
            elif current and line.startswith("inet "):
                im = re.match(r"inet\s+([\d.]+)/(\d+)", line)
                if im:
                    current["ip"] = f"{im.group(1)}/{im.group(2)}"
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        pass
    return interfaces


_SORTABLE_FIELDS = ("ip", "mac", "hostname", "starts", "ends", "state", "name")


def _collect_dhcp(
    server: str = "",
    q: str = "",
    state: str = "",
    sort_by: str = "ip",
    sort_dir: str = "asc",
    page: int = 1,
    page_size: int = 50,
) -> dict:
    """DHCP 租约收集与处理的同步核心。

    优先读取 Windows DHCP 服务器推送的快照数据；
    若无快照则回退到本地租约文件（ISC/dnsmasq）。
    注入姓名映射/MAC 归一化、过滤、排序、分页，同时返回本机网卡信息。
    """
    servers = list_dhcp_servers()
    leases: list[dict] = []
    source = ""
    collected_at = ""
    current_server = ""

    if servers:
        # 有推送数据：选择服务器
        current_server = server or servers[0]["id"]
        snap = _load_latest_snapshot(current_server)
        if snap:
            leases = _snapshot_to_leases(snap)
            source = f"推送：{snap.get('server', current_server)}"
            collected_at = snap.get("collectedAt", "")
    else:
        # 无推送数据：回退本地租约文件
        lease_files = [p.strip() for p in settings.dhcp_lease_files.split(",") if p.strip()]
        for path in lease_files:
            try:
                with open(path, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
            except OSError:
                continue
            if "lease " in content and "{" in content:
                leases = _parse_isc_leases(content)
                source = path
            else:
                parsed = _parse_dnsmasq_leases(content)
                if parsed:
                    leases = parsed
                    source = path
            if leases:
                break

    # 注入姓名映射 + MAC 归一化
    namemap = _load_namemap()
    enriched: list[dict] = []
    for item in leases:
        row = dict(item)
        row["mac"] = _format_mac(item.get("mac"))
        row["name"] = _match_name(item, namemap)
        enriched.append(row)

    # 状态过滤
    if state:
        enriched = [l for l in enriched if (l.get("state") or "").lower() == state.lower()]

    # 搜索（IP / MAC / 主机名 / 姓名）
    if q:
        needle = q.lower()
        enriched = [
            l for l in enriched
            if needle in (l.get("ip") or "").lower()
            or needle in (l.get("mac") or "").lower()
            or needle in (l.get("hostname") or "").lower()
            or needle in (l.get("name") or "").lower()
        ]

    # 排序
    key_field = sort_by if sort_by in _SORTABLE_FIELDS else "ip"
    reverse = sort_dir.lower() == "desc"

    def _sort_key(item: dict):
        v = str(item.get(key_field) or "")
        if key_field == "ip":
            try:
                return tuple(int(p) for p in v.split("."))
            except ValueError:
                return (0,)
        return v.lower()

    enriched.sort(key=_sort_key, reverse=reverse)

    total = len(enriched)
    start = (page - 1) * page_size
    items = enriched[start:start + page_size]

    interfaces = _get_local_interfaces()

    return {
        "lease_source": source,
        "collected_at": collected_at,
        "current_server": current_server,
        "servers": servers,
        "total": total,
        "page": page,
        "page_size": page_size,
        "lease_count": len(leases),
        "leases": items,
        "interfaces": interfaces,
        "states": ["active", "inactive", "reserved", "declined"],
    }


async def get_dhcp_info(
    server: str = "",
    q: str = "",
    state: str = "",
    sort_by: str = "ip",
    sort_dir: str = "asc",
    page: int = 1,
    page_size: int = 50,
) -> dict:
    """获取 DHCP 租约信息（支持服务器选择、搜索、状态过滤、排序、分页）与本机网卡信息。"""
    return _collect_dhcp(server=server, q=q, state=state, sort_by=sort_by, sort_dir=sort_dir,
                         page=page, page_size=page_size)


def export_dhcp_leases(server: str = "", q: str = "", state: str = "", fmt: str = "csv") -> tuple[bytes, str, str]:
    """导出 DHCP 租约为 CSV / XLSX。返回 (内容字节, media_type, 文件名)。"""
    info = _collect_dhcp(server=server, q=q, state=state, sort_by="ip", sort_dir="asc", page=1, page_size=100000)
    rows = info["leases"]

    cols = [("hostname", "主机名"), ("state", "地址状态"), ("ends", "租期"), ("mac", "MAC地址"), ("ip", "IP地址"), ("name", "姓名")]
    if fmt == "csv":
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow([label for _, label in cols])
        for r in rows:
            w.writerow([r.get(k, "") for k, _ in cols])
        content = ("\ufeff" + buf.getvalue()).encode("utf-8")
        return content, "text/csv; charset=utf-8", "dhcp_leases.csv"

    # xlsx 导出（需 openpyxl）
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Alignment, Font, PatternFill
        from openpyxl.utils import get_column_letter
    except ImportError:
        # 无 openpyxl 时回退到 CSV
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow([label for _, label in cols])
        for r in rows:
            w.writerow([r.get(k, "") for k, _ in cols])
        content = ("\ufeff" + buf.getvalue()).encode("utf-8")
        return content, "text/csv; charset=utf-8", "dhcp_leases.csv"

    wb = Workbook()
    ws = wb.active
    ws.title = "DHCP Leases"
    head_font = Font(bold=True, color="FFFFFF")
    head_fill = PatternFill("solid", fgColor="2563EB")
    for ci, (_, label) in enumerate(cols, start=1):
        c = ws.cell(row=1, column=ci, value=label)
        c.font = head_font
        c.fill = head_fill
        c.alignment = Alignment(horizontal="center", vertical="center")
    for ri, r in enumerate(rows, start=2):
        for ci, (k, _) in enumerate(cols, start=1):
            ws.cell(row=ri, column=ci, value=r.get(k, ""))
    for i, width in enumerate((26, 12, 22, 22, 18, 12), start=1):
        ws.column_dimensions[get_column_letter(i)].width = width
    ws.freeze_panes = "A2"

    out = io.BytesIO()
    wb.save(out)
    return out.getvalue(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "dhcp_leases.xlsx"
