"""AI 分析异步任务入口（fire-and-forget，单实例内存队列）。"""
from __future__ import annotations

import asyncio
import logging

logger = logging.getLogger(__name__)

# 持有后台任务强引用，避免任务被 GC 提前回收；完成后自动移除
_tasks: set[asyncio.Task] = set()


def submit_analysis(alert_id: int) -> bool:
    """把分析任务投递到事件循环，不阻塞调用方。返回是否投递成功。"""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        logger.error("无运行中的事件循环，无法提交分析任务 alert_id=%s", alert_id)
        return False
    task = loop.create_task(_run(alert_id))
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)
    return True


async def _run(alert_id: int) -> None:
    try:
        from app.services import analysis_service
        await analysis_service.run_analysis(alert_id)
    except Exception:  # noqa: BLE001
        logger.exception("分析任务执行异常 alert_id=%s", alert_id)
