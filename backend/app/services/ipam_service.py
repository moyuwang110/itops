"""IPAM 服务：网段 / VLAN / IP 地址 / 变更记录，含自动扫描与冲突检测。"""
from __future__ import annotations

import ipaddress
import logging
from typing import Any

from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BizError
from app.core.timeutil import to_iso, utcnow
from app.models.ipam import IPAddress, IPChangeLog, Subnet, Vlan
from app.services import network_tool_service

logger = logging.getLogger(__name__)

VALID_STATUS = {"used", "free", "unknown", "conflict", "reserved"}


# ---------- 序列化 ----------


def _subnet_row(s: Subnet, vlan: Vlan | None) -> dict[str, Any]:
    return {
        "id": s.id,
        "name": s.name,
        "cidr": s.cidr,
        "gateway": s.gateway,
        "purpose": s.purpose,
        "vlan_ref": s.vlan_ref,
        "vlan_id": vlan.vlan_id if vlan else None,
        "vlan_name": vlan.name if vlan else "",
        "remark": s.remark,
        "auto_scan": bool(s.auto_scan),
        "last_scan_at": to_iso(s.last_scan_at),
        "total": s.total,
        "used": s.used,
        "free": s.free,
        "unknown": s.unknown,
        "conflict": s.conflict,
        "reserved": s.reserved,
        "utilization": s.utilization,
        "created_at": to_iso(s.created_at),
    }


def _addr_row(a: IPAddress) -> dict[str, Any]:
    return {
        "id": a.id,
        "subnet_id": a.subnet_id,
        "ip": a.ip,
        "status": a.status,
        "mac": a.mac,
        "hostname": a.hostname,
        "assigned_to": a.assigned_to,
        "purpose": a.purpose,
        "remark": a.remark,
        "source": a.source,
        "open_ports": a.open_ports or [],
        "response_ms": a.response_ms,
        "first_seen_at": to_iso(a.first_seen_at),
        "last_seen_at": to_iso(a.last_seen_at),
        "last_scan_at": to_iso(a.last_scan_at),
        "conflict": bool(a.conflict_reason),
        "conflict_reason": a.conflict_reason or "",
        "change_count": a.change_count,
    }


def _vlan_row(v: Vlan) -> dict[str, Any]:
    return {
        "id": v.id,
        "vlan_id": v.vlan_id,
        "name": v.name,
        "remark": v.remark,
        "created_at": to_iso(v.created_at),
    }


def _log_row(l: IPChangeLog) -> dict[str, Any]:
    return {
        "id": l.id,
        "subnet_id": l.subnet_id,
        "ip": l.ip,
        "action": l.action,
        "field": l.field,
        "old_value": l.old_value,
        "new_value": l.new_value,
        "operator": l.operator,
        "detail": l.detail,
        "created_at": to_iso(l.created_at),
    }


def _add_log(db: AsyncSession, subnet_id: int, ip: str, action: str,
             field: str = "", old_value: str = "", new_value: str = "",
             operator: str = "system", detail: str = "") -> None:
    db.add(IPChangeLog(
        subnet_id=subnet_id, ip=ip, action=action, field=field,
        old_value=old_value, new_value=new_value,
        operator=operator, detail=detail,
    ))


# ---------- VLAN ----------


async def list_vlans(db: AsyncSession) -> list[dict[str, Any]]:
    rows = (await db.execute(select(Vlan).order_by(Vlan.vlan_id))).scalars().all()
    counts = dict((await db.execute(
        select(Subnet.vlan_ref, func.count(Subnet.id)).group_by(Subnet.vlan_ref)
    )).all())
    out = []
    for v in rows:
        row = _vlan_row(v)
        row["subnet_count"] = int(counts.get(v.id, 0) or 0)
        out.append(row)
    return out


async def create_vlan(db: AsyncSession, payload: dict[str, Any]) -> dict[str, Any]:
    try:
        vlan_id = int(payload.get("vlan_id"))
    except (TypeError, ValueError):
        raise BizError("VLAN ID 必须是 1-4094 之间的整数", code="bad_request") from None
    if not 1 <= vlan_id <= 4094:
        raise BizError("VLAN ID 必须是 1-4094 之间的整数", code="bad_request")
    exists = (await db.execute(select(Vlan).where(Vlan.vlan_id == vlan_id))).scalar_one_or_none()
    if exists:
        raise BizError(f"VLAN {vlan_id} 已存在", code="duplicate")
    vlan = Vlan(vlan_id=vlan_id,
                name=str(payload.get("name") or "").strip(),
                remark=str(payload.get("remark") or "").strip())
    db.add(vlan)
    await db.commit()
    await db.refresh(vlan)
    return _vlan_row(vlan)


async def update_vlan(db: AsyncSession, vlan_pk: int, payload: dict[str, Any]) -> dict[str, Any]:
    vlan = await db.get(Vlan, vlan_pk)
    if vlan is None:
        raise BizError("VLAN 不存在", code="not_found", http_status=404)
    if "vlan_id" in payload and payload["vlan_id"] is not None:
        try:
            new_id = int(payload["vlan_id"])
        except (TypeError, ValueError):
            raise BizError("VLAN ID 必须是 1-4094 之间的整数", code="bad_request") from None
        if not 1 <= new_id <= 4094:
            raise BizError("VLAN ID 必须是 1-4094 之间的整数", code="bad_request")
        if new_id != vlan.vlan_id:
            dup = (await db.execute(select(Vlan).where(Vlan.vlan_id == new_id))).scalar_one_or_none()
            if dup:
                raise BizError(f"VLAN {new_id} 已存在", code="duplicate")
            vlan.vlan_id = new_id
    if payload.get("name") is not None:
        vlan.name = str(payload["name"]).strip()
    if payload.get("remark") is not None:
        vlan.remark = str(payload["remark"]).strip()
    await db.commit()
    await db.refresh(vlan)
    return _vlan_row(vlan)


async def delete_vlan(db: AsyncSession, vlan_pk: int) -> None:
    vlan = await db.get(Vlan, vlan_pk)
    if vlan is None:
        raise BizError("VLAN 不存在", code="not_found", http_status=404)
    # 解绑引用该 VLAN 的网段，避免悬空引用
    subs = (await db.execute(select(Subnet).where(Subnet.vlan_ref == vlan_pk))).scalars().all()
    for s in subs:
        s.vlan_ref = None
    await db.delete(vlan)
    await db.commit()


# ---------- 网段 ----------


async def list_subnets(db: AsyncSession) -> list[dict[str, Any]]:
    subs = (await db.execute(select(Subnet).order_by(Subnet.cidr))).scalars().all()
    vlan_map = {v.id: v for v in (await db.execute(select(Vlan))).scalars().all()}
    return [_subnet_row(s, vlan_map.get(s.vlan_ref) if s.vlan_ref else None) for s in subs]


def _parse_cidr(cidr: str) -> ipaddress.IPv4Network:
    try:
        net = ipaddress.ip_network((cidr or "").strip(), strict=False)
    except ValueError as exc:
        raise BizError(f"无效的 CIDR：{cidr}", code="bad_request") from exc
    if net.version != 4:
        raise BizError("仅支持 IPv4 网段", code="bad_request")
    if net.num_addresses > 65536:
        raise BizError("网段过大，最多支持 /16（65536 个地址）", code="bad_request")
    return net


async def create_subnet(db: AsyncSession, payload: dict[str, Any]) -> dict[str, Any]:
    cidr = str(payload.get("cidr") or "").strip()
    net = _parse_cidr(cidr)
    cidr = str(net)
    dup = (await db.execute(select(Subnet).where(Subnet.cidr == cidr))).scalar_one_or_none()
    if dup:
        raise BizError(f"网段 {cidr} 已存在", code="duplicate")
    gateway = str(payload.get("gateway") or "").strip()
    if gateway:
        try:
            if ipaddress.ip_address(gateway) not in net:
                raise BizError("网关地址不在该网段内", code="bad_request")
        except ValueError as exc:
            raise BizError(f"无效的网关地址：{gateway}", code="bad_request") from exc
    hosts = list(net.hosts()) if net.num_addresses > 2 else list(net)
    subnet = Subnet(
        name=str(payload.get("name") or cidr).strip(),
        cidr=cidr,
        gateway=gateway,
        purpose=str(payload.get("purpose") or "").strip(),
        vlan_ref=payload.get("vlan_ref") or None,
        remark=str(payload.get("remark") or "").strip(),
        auto_scan=bool(payload.get("auto_scan", True)),
        total=len(hosts),
        free=len(hosts),
    )
    db.add(subnet)
    await db.commit()
    await db.refresh(subnet)
    vlan = await db.get(Vlan, subnet.vlan_ref) if subnet.vlan_ref else None
    return _subnet_row(subnet, vlan)


async def update_subnet(db: AsyncSession, subnet_pk: int, payload: dict[str, Any]) -> dict[str, Any]:
    subnet = await db.get(Subnet, subnet_pk)
    if subnet is None:
        raise BizError("网段不存在", code="not_found", http_status=404)
    if payload.get("name") is not None:
        subnet.name = str(payload["name"]).strip()
    if payload.get("gateway") is not None:
        gateway = str(payload["gateway"]).strip()
        if gateway:
            try:
                if ipaddress.ip_address(gateway) not in ipaddress.ip_network(subnet.cidr):
                    raise BizError("网关地址不在该网段内", code="bad_request")
            except ValueError as exc:
                raise BizError(f"无效的网关地址：{gateway}", code="bad_request") from exc
        subnet.gateway = gateway
    if payload.get("purpose") is not None:
        subnet.purpose = str(payload["purpose"]).strip()
    if "vlan_ref" in payload:
        subnet.vlan_ref = payload["vlan_ref"] or None
    if payload.get("remark") is not None:
        subnet.remark = str(payload["remark"]).strip()
    if payload.get("auto_scan") is not None:
        subnet.auto_scan = bool(payload["auto_scan"])
    await db.commit()
    await db.refresh(subnet)
    vlan = await db.get(Vlan, subnet.vlan_ref) if subnet.vlan_ref else None
    return _subnet_row(subnet, vlan)


async def delete_subnet(db: AsyncSession, subnet_pk: int) -> None:
    subnet = await db.get(Subnet, subnet_pk)
    if subnet is None:
        raise BizError("网段不存在", code="not_found", http_status=404)
    await db.execute(delete(IPAddress).where(IPAddress.subnet_id == subnet_pk))
    await db.execute(delete(IPChangeLog).where(IPChangeLog.subnet_id == subnet_pk))
    await db.delete(subnet)
    await db.commit()


# ---------- IP 地址 ----------


async def list_addresses(db: AsyncSession, subnet_id: int, status: str = "",
                         keyword: str = "", only_conflict: bool = False,
                         page: int = 1, page_size: int = 100) -> dict[str, Any]:
    conditions = [IPAddress.subnet_id == subnet_id]
    if status:
        if status not in VALID_STATUS:
            raise BizError(f"无效的状态：{status}", code="bad_request")
        conditions.append(IPAddress.status == status)
    if only_conflict:
        conditions.append(IPAddress.conflict_reason != "")
    if keyword:
        like = f"%{keyword.strip()}%"
        conditions.append(or_(
            IPAddress.ip.like(like),
            IPAddress.mac.like(like),
            IPAddress.hostname.like(like),
            IPAddress.assigned_to.like(like),
        ))
    total = (await db.execute(
        select(func.count(IPAddress.id)).where(*conditions)
    )).scalar_one()
    rows = (await db.execute(
        select(IPAddress).where(*conditions)
        .order_by(IPAddress.id).offset((page - 1) * page_size).limit(page_size)
    )).scalars().all()
    return {"total": total, "page": page, "page_size": page_size,
            "items": [_addr_row(a) for a in rows]}


async def subnet_addresses_all(db: AsyncSession, subnet_id: int) -> list[dict[str, Any]]:
    rows = (await db.execute(
        select(IPAddress).where(IPAddress.subnet_id == subnet_id).order_by(IPAddress.id)
    )).scalars().all()
    return [_addr_row(a) for a in rows]


async def manual_assign(db: AsyncSession, payload: dict[str, Any],
                        operator: str = "admin") -> dict[str, Any]:
    """手工登记 / 分配 IP。"""
    try:
        subnet_id = int(payload.get("subnet_id"))
    except (TypeError, ValueError):
        raise BizError("subnet_id 必填", code="bad_request") from None
    ip = str(payload.get("ip") or "").strip()
    subnet = await db.get(Subnet, subnet_id)
    if subnet is None:
        raise BizError("网段不存在", code="not_found", http_status=404)
    net = _parse_cidr(subnet.cidr)
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError as exc:
        raise BizError(f"无效的 IP：{ip}", code="bad_request") from exc
    if addr not in net:
        raise BizError(f"IP {ip} 不在网段 {subnet.cidr} 内", code="bad_request")
    ip = str(addr)

    existing = (await db.execute(select(IPAddress).where(
        IPAddress.subnet_id == subnet_id, IPAddress.ip == ip
    ))).scalar_one_or_none()

    assigned_to = str(payload.get("assigned_to") or "").strip()
    purpose = str(payload.get("purpose") or "").strip()
    remark = str(payload.get("remark") or "").strip()
    now = utcnow()

    if existing is None:
        record = IPAddress(
            subnet_id=subnet_id, ip=ip, status="reserved",
            mac=str(payload.get("mac") or "").strip(),
            hostname=str(payload.get("hostname") or "").strip(),
            assigned_to=assigned_to, purpose=purpose, remark=remark,
            source="manual", first_seen_at=now, last_seen_at=now,
        )
        db.add(record)
        await db.flush()
        _add_log(db, subnet_id, ip, "assign", operator=operator,
                 detail=f"手工登记 IP，责任人 {assigned_to or '-'}")
        created = record
    else:
        old_status = existing.status
        old_owner = existing.assigned_to
        existing.assigned_to = assigned_to
        existing.purpose = purpose
        existing.remark = remark
        if payload.get("mac"):
            existing.mac = str(payload["mac"]).strip()
        if payload.get("hostname"):
            existing.hostname = str(payload["hostname"]).strip()
        # 手工登记的地址标记为保留；扫描后续会重新判定在线状态
        if old_status in ("free", "unknown"):
            existing.status = "reserved"
        existing.source = "manual"
        existing.change_count = (existing.change_count or 0) + 1
        _add_log(db, subnet_id, ip, "assign", field="assigned_to",
                 old_value=old_owner, new_value=assigned_to, operator=operator,
                 detail="更新手工登记信息")
        created = existing
    await db.commit()
    await db.refresh(created)
    await refresh_subnet_stats(db, subnet_id)
    return _addr_row(created)


async def release_ip(db: AsyncSession, ip_pk: int, operator: str = "admin") -> dict[str, Any]:
    record = await db.get(IPAddress, ip_pk)
    if record is None:
        raise BizError("IP 记录不存在", code="not_found", http_status=404)
    old_owner = record.assigned_to
    record.assigned_to = ""
    record.purpose = ""
    record.remark = ""
    record.source = "auto"
    record.conflict_reason = ""
    record.change_count = (record.change_count or 0) + 1
    _add_log(db, record.subnet_id, record.ip, "release", field="assigned_to",
             old_value=old_owner, new_value="", operator=operator,
             detail="释放手工登记")
    await db.commit()
    await db.refresh(record)
    await refresh_subnet_stats(db, record.subnet_id)
    return _addr_row(record)


# ---------- 扫描 ----------


async def scan_subnet(db: AsyncSession, subnet_pk: int) -> dict[str, Any]:
    subnet = await db.get(Subnet, subnet_pk)
    if subnet is None:
        raise BizError("网段不存在", code="not_found", http_status=404)
    try:
        result = await network_tool_service.scan_addresses(subnet.cidr)
    except ValueError as exc:
        raise BizError(str(exc), code="bad_request") from exc

    now = utcnow()
    existing_rows = (await db.execute(
        select(IPAddress).where(IPAddress.subnet_id == subnet_pk)
    )).scalars().all()
    by_ip = {r.ip: r for r in existing_rows}

    for item in result.get("addresses", []):
        ip = item["ip"]
        status = item.get("status") or "free"
        mac = item.get("mac") or ""
        hostname = item.get("hostname") or ""
        record = by_ip.get(ip)
        if record is None:
            record = IPAddress(
                subnet_id=subnet_pk, ip=ip, status=status, mac=mac,
                hostname=hostname, source="auto",
                open_ports=item.get("open_ports") or [],
                response_ms=item.get("response_ms"),
                first_seen_at=now if status == "used" else None,
                last_seen_at=now if status == "used" else None,
                last_scan_at=now,
            )
            db.add(record)
            if status == "used":
                _add_log(db, subnet_pk, ip, "scan_new",
                         new_value=f"{hostname or '-'} {mac or ''}".strip(),
                         detail="每日扫描发现的新地址")
            continue

        # 只保留手工登记的责任人/用途/备注，扫描字段照常刷新
        old_status, old_mac, old_host = record.status, record.mac, record.hostname
        record.last_scan_at = now
        record.response_ms = item.get("response_ms")
        record.open_ports = item.get("open_ports") or []
        if status == "used":
            record.last_seen_at = now
            if record.first_seen_at is None:
                record.first_seen_at = now
        if record.source != "manual":
            record.status = status
        elif status == "used":
            # 手工登记的地址扫描到在线，以扫描状态为准
            record.status = "used"
        elif status == "free":
            # 手工登记但扫描未发现，回到空闲并保留登记信息（由冲突检测提示）
            record.status = "free"
        if mac and mac != old_mac:
            record.mac = mac
            _add_log(db, subnet_pk, ip, "scan_update", field="mac",
                     old_value=old_mac, new_value=mac, detail="MAC 变更")
        if hostname and hostname != old_host:
            record.hostname = hostname
            _add_log(db, subnet_pk, ip, "scan_update", field="hostname",
                     old_value=old_host, new_value=hostname, detail="主机名变更")
        if old_status != record.status:
            _add_log(db, subnet_pk, ip, "status_change", field="status",
                     old_value=old_status, new_value=record.status,
                     detail="扫描状态变更")

    subnet.last_scan_at = now
    await db.flush()
    await _detect_conflicts(db, subnet_pk)
    await db.commit()
    await refresh_subnet_stats(db, subnet_pk)
    await db.refresh(subnet)
    vlan = await db.get(Vlan, subnet.vlan_ref) if subnet.vlan_ref else None
    return {
        "subnet": _subnet_row(subnet, vlan),
        "scan": {
            "cidr": result.get("cidr"),
            "total": result.get("total"),
            "used": result.get("used"),
            "conflict": result.get("conflict"),
            "last_scan": result.get("last_scan"),
        },
        "conflicts": await list_conflicts(db, subnet_pk),
    }


async def scan_all_subnets(db: AsyncSession) -> dict[str, Any]:
    """每日自动扫描：遍历所有启用自动扫描的网段。"""
    subs = (await db.execute(select(Subnet).where(Subnet.auto_scan.is_(True)))).scalars().all()
    ok, failed = 0, []
    for s in subs:
        try:
            await scan_subnet(db, s.id)
            ok += 1
        except Exception as exc:  # noqa: BLE001
            logger.exception("自动扫描网段 %s 失败", s.cidr)
            failed.append({"cidr": s.cidr, "error": str(exc)})
    logger.info("IPAM 自动扫描完成：成功 %d，失败 %d", ok, len(failed))
    return {"scanned": ok, "failed": failed}


async def _detect_conflicts(db: AsyncSession, subnet_pk: int) -> None:
    """冲突检测：重复 MAC、手工登记与扫描结果不一致。"""
    rows = (await db.execute(
        select(IPAddress).where(IPAddress.subnet_id == subnet_pk)
    )).scalars().all()

    # 1. 同一 MAC 出现在多个 IP 上
    mac_map: dict[str, list[IPAddress]] = {}
    for r in rows:
        if r.mac and r.status in ("used", "conflict"):
            mac_map.setdefault(r.mac.upper(), []).append(r)
    conflicts: dict[int, str] = {}
    for mac, items in mac_map.items():
        if len(items) > 1:
            ips = ", ".join(i.ip for i in items)
            for i in items:
                conflicts[i.id] = f"MAC 重复：{mac} 同时出现在 {ips}"

    # 2. 手工登记了责任人，但扫描未发现该地址在线
    for r in rows:
        if r.assigned_to and r.status == "free" and r.last_scan_at:
            conflicts.setdefault(r.id, "已登记责任人，但扫描未发现该地址在线")

    for r in rows:
        reason = conflicts.get(r.id, "")
        if r.conflict_reason != reason:
            if reason:
                _add_log(db, subnet_pk, r.ip, "conflict", field="conflict_reason",
                         old_value=r.conflict_reason, new_value=reason,
                         detail="检测到地址冲突")
            r.conflict_reason = reason
    await db.flush()


async def list_conflicts(db: AsyncSession, subnet_id: int | None = None) -> list[dict[str, Any]]:
    conditions = [IPAddress.conflict_reason != ""]
    if subnet_id:
        conditions.append(IPAddress.subnet_id == subnet_id)
    rows = (await db.execute(
        select(IPAddress).where(*conditions).order_by(IPAddress.ip).limit(500)
    )).scalars().all()
    subnet_names = {
        s.id: (s.name or s.cidr) for s in (await db.execute(select(Subnet))).scalars().all()
    }
    out = []
    for r in rows:
        item = _addr_row(r)
        item["subnet_name"] = subnet_names.get(r.subnet_id, "")
        out.append(item)
    return out


async def refresh_subnet_stats(db: AsyncSession, subnet_pk: int) -> None:
    """按库内记录重算网段扫描统计。"""
    subnet = await db.get(Subnet, subnet_pk)
    if subnet is None:
        return
    rows = (await db.execute(
        select(IPAddress.status, func.count(IPAddress.id))
        .where(IPAddress.subnet_id == subnet_pk).group_by(IPAddress.status)
    )).all()
    stats = {status: int(cnt) for status, cnt in rows}
    subnet.used = stats.get("used", 0)
    subnet.free = stats.get("free", 0)
    subnet.unknown = stats.get("unknown", 0)
    subnet.conflict = stats.get("conflict", 0)
    subnet.reserved = stats.get("reserved", 0)
    subnet.total = sum(stats.values()) or subnet.total
    subnet.utilization = round(
        (subnet.used + subnet.reserved) / subnet.total * 100, 1
    ) if subnet.total else 0.0
    await db.commit()


# ---------- 变更记录 ----------


async def list_changelogs(db: AsyncSession, subnet_id: int | None = None,
                          ip: str = "", page: int = 1, page_size: int = 50) -> dict[str, Any]:
    conditions = []
    if subnet_id:
        conditions.append(IPChangeLog.subnet_id == subnet_id)
    if ip:
        conditions.append(IPChangeLog.ip == ip)
    total = (await db.execute(
        select(func.count(IPChangeLog.id)).where(*conditions)
    )).scalar_one()
    rows = (await db.execute(
        select(IPChangeLog).where(*conditions)
        .order_by(IPChangeLog.created_at.desc(), IPChangeLog.id.desc())
        .offset((page - 1) * page_size).limit(page_size)
    )).scalars().all()
    return {"total": total, "page": page, "page_size": page_size,
            "items": [_log_row(r) for r in rows]}
