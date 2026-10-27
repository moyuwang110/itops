"""v1 路由聚合。"""
from fastapi import APIRouter

from app.api.v1 import (
    agents,
    alerts,
    auth,
    cmdb,
    configs,
    dashboard,
    health,
    ipam,
    logs,
    network_tools,
    reports,
    vmware,
    webhooks,
    zabbix,
)

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(health.router, tags=["system"])
api_router.include_router(auth.router)
api_router.include_router(configs.router)
api_router.include_router(zabbix.router)
api_router.include_router(webhooks.router)
api_router.include_router(alerts.router)
api_router.include_router(reports.router)
api_router.include_router(logs.router)
api_router.include_router(dashboard.router)
api_router.include_router(agents.router)
api_router.include_router(vmware.router)
api_router.include_router(cmdb.router)
api_router.include_router(ipam.router)
api_router.include_router(network_tools.router)
api_router.include_router(network_tools.public_router)
