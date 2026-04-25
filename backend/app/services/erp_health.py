import asyncio
import logging
from datetime import datetime
from typing import Any

import httpx

from app.ncloud.client.erp_client import ERPClient
from app.ncloud.config import settings as ncloud_settings

logger = logging.getLogger(__name__)

_poll_task: asyncio.Task | None = None
_check_lock = asyncio.Lock()
_status: dict[str, Any] = {
    "online": False,
    "last_checked_at": None,
    "last_error": "尚未检测",
}


async def _check_once() -> None:
    base_url = (ncloud_settings.NCLOUD_BASE_URL or "").strip().rstrip("/")
    if not base_url:
        _status.update({
            "online": False,
            "last_checked_at": datetime.now().isoformat(),
            "last_error": "未配置 ERP 基础地址",
        })
        return

    if not (ncloud_settings.NCLOUD_USERNAME and ncloud_settings.NCLOUD_PASSWORD):
        _status.update({
            "online": False,
            "last_checked_at": datetime.now().isoformat(),
            "last_error": "未配置 ERP 登录账号或密码",
        })
        return

    try:
        async with httpx.AsyncClient(timeout=8, follow_redirects=True, trust_env=False) as client:
            erp_client = ERPClient(client)

            # 步骤1：登录校验
            await erp_client._auth.login(force=True)

            # 步骤2：获取状态信息（账套信息）
            account_set = await erp_client._auth.resolve_account_set()

        if not account_set.get("account_set_name"):
            _status.update({
                "online": False,
                "last_checked_at": datetime.now().isoformat(),
                "last_error": "获取 ERP 状态信息失败：缺少账套名称",
            })
            return

        _status.update({
            "online": True,
            "last_checked_at": datetime.now().isoformat(),
            "last_error": None,
        })
    except Exception as exc:
        _status.update({
            "online": False,
            "last_checked_at": datetime.now().isoformat(),
            "last_error": str(exc),
        })


async def refresh_erp_health_status() -> dict[str, Any]:
    """立即执行一次 ERP 状态检查并返回最新状态"""
    async with _check_lock:
        await _check_once()
        return get_erp_health_status()


async def _poll_loop(interval_seconds: int) -> None:
    while True:
        await refresh_erp_health_status()
        await asyncio.sleep(interval_seconds)


def start_erp_health_checker(interval_seconds: int = 30) -> None:
    global _poll_task
    if _poll_task and not _poll_task.done():
        return
    _poll_task = asyncio.create_task(_poll_loop(interval_seconds))
    logger.info("[ERP Health] 已启动健康检查轮询，间隔 %s 秒", interval_seconds)


def stop_erp_health_checker() -> None:
    global _poll_task
    if _poll_task and not _poll_task.done():
        _poll_task.cancel()
    _poll_task = None


def get_erp_health_status() -> dict[str, Any]:
    return {
        "online": bool(_status.get("online", False)),
        "last_checked_at": _status.get("last_checked_at"),
        "last_error": _status.get("last_error"),
        "polling": _poll_task is not None and not _poll_task.done() if _poll_task else False,
    }
