"""运维工具箱：地址扫描、DHCP 信息查询（需登录）。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Header, Query
from fastapi.responses import Response

from app.api.deps import get_current_user
from app.core.exceptions import BizError
from app.services import network_tool_service

# 需登录的路由
router = APIRouter(prefix="/network-tools", tags=["network-tools"],
                   dependencies=[Depends(get_current_user)])

# 公开路由（供 Windows DHCP 服务器推送脚本调用，使用 X-Auth-Token 鉴权）
public_router = APIRouter(prefix="/network-tools", tags=["network-tools-public"])


@router.get("/scan", summary="地址扫描（仅私网）")
async def scan(
    cidr: str = Query(..., min_length=1, description="CIDR，如 192.168.1.0/24"),
) -> dict:
    try:
        return await network_tool_service.scan_addresses(cidr)
    except ValueError as exc:
        raise BizError(str(exc), code="bad_request", http_status=400)


@router.get("/dhcp", summary="DHCP 租约与网卡信息")
async def dhcp(
    server: str = Query("", description="DHCP 服务器 ID（留空取第一个）"),
    q: str = Query("", description="搜索：IP/主机名/MAC/姓名"),
    state: str = Query("", description="地址状态过滤：active/inactive/reserved/declined"),
    sort_by: str = Query("ip", description="排序字段"),
    sort_dir: str = Query("asc", description="asc / desc"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
) -> dict:
    return await network_tool_service.get_dhcp_info(
        server=server, q=q, state=state, sort_by=sort_by, sort_dir=sort_dir,
        page=page, page_size=page_size,
    )


@router.get("/dhcp/servers", summary="DHCP 服务器列表")
async def dhcp_servers() -> dict:
    return {"servers": network_tool_service.list_dhcp_servers()}


@router.get("/dhcp/export", summary="导出 DHCP 租约（CSV / XLSX）")
async def dhcp_export(
    server: str = Query(""),
    q: str = Query(""),
    state: str = Query(""),
    fmt: str = Query("csv", description="csv / xlsx"),
) -> Response:
    content, media_type, filename = network_tool_service.export_dhcp_leases(
        server=server, q=q, state=state, fmt=fmt)
    disposition = f'attachment; filename="{filename}"'
    return Response(content=content, media_type=media_type, headers={"Content-Disposition": disposition})


# ---------- 姓名映射 ----------


@router.get("/dhcp/namemap", summary="姓名映射列表")
async def namemap_list() -> dict:
    return {"items": network_tool_service.list_namemap()}


@router.post("/dhcp/namemap", summary="新增/更新姓名映射")
async def namemap_add(payload: dict) -> dict:
    try:
        return network_tool_service.add_namemap(payload.get("key", ""), payload.get("name", ""))
    except ValueError as exc:
        raise BizError(str(exc), code="bad_request", http_status=400)


@router.delete("/dhcp/namemap", summary="删除姓名映射")
async def namemap_delete(key: str = Query(...)) -> dict:
    try:
        return network_tool_service.delete_namemap(key)
    except ValueError as exc:
        raise BizError(str(exc), code="bad_request", http_status=400)


# ---------- DHCP 数据上传（公开，X-Auth-Token 鉴权） ----------


@public_router.post("/dhcp/upload", summary="Windows DHCP 服务器推送租约数据")
async def dhcp_upload(
    payload: dict,
    x_auth_token: str | None = Header(default=None, alias="X-Auth-Token"),
) -> dict:
    try:
        return network_tool_service.receive_dhcp_upload(payload, x_auth_token or "")
    except PermissionError:
        raise BizError("无效的上传令牌", code="unauthorized", http_status=401)
    except ValueError as exc:
        raise BizError(str(exc), code="bad_request", http_status=400)
