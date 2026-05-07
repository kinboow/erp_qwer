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
_prev_online: bool | None = None  # 用于检测状态变化


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
    global _prev_online
    async with _check_lock:
        await _check_once()
        current_online = _status.get("online", False)

        # 状态由在线变为离线时，写入紧急系统动态 + 系统消息 + 语音告警
        if _prev_online is not None and _prev_online and not current_online:
            error_msg = _status.get("last_error") or "未知原因"
            try:
                from app.services.system_activities import create_activity_background
                create_activity_background(
                    title="ERP 连接服务离线",
                    content=f"ERP 连接检测失败：{error_msg}",
                    type="urgent",
                    source="erp_health",
                )
            except Exception:
                pass
            try:
                from app.services.system_messages import create_system_message_background
                create_system_message_background(
                    title="ERP 连接离线",
                    content=f"ERP 连接检测失败：{error_msg}，请检查 ERP 服务状态",
                    level="error",
                    source="erp_health",
                )
            except Exception:
                pass
            # 服务器语音告警
            try:
                from app.services.voice_alert import speak_alert
                speak_alert("ERP已掉线，请快速处理！", repeat=3)
            except Exception:
                pass
            # 通知前端
            try:
                from app.services import ws_notify
                await ws_notify.broadcast("erp_offline", {"error": error_msg})
            except Exception:
                pass
            # 通知群推送
            try:
                from app.services.notify_group import send_to_notification_groups
                await send_to_notification_groups(None, f"🔴 ERP 连接离线\n原因：{error_msg}\n请尽快检查 ERP 服务状态！")
            except Exception:
                pass

        # 状态由离线变为在线时，写入系统消息 + 通知前端
        if _prev_online is not None and not _prev_online and current_online:
            try:
                from app.services.system_messages import create_system_message_background
                create_system_message_background(
                    title="ERP 连接已恢复",
                    content="ERP 连接已恢复正常",
                    level="info",
                    source="erp_health",
                )
            except Exception:
                pass
            try:
                from app.services import ws_notify
                await ws_notify.broadcast("erp_online")
            except Exception:
                pass
            try:
                from app.services.notify_group import send_to_notification_groups
                await send_to_notification_groups(None, "✅ ERP 连接已恢复\nERP 服务已恢复正常，可继续同步和下单。")
            except Exception:
                pass

        _prev_online = current_online
        return get_erp_health_status()


async def _poll_loop(interval_seconds: int) -> None:
    while True:
        await refresh_erp_health_status()
        await asyncio.sleep(interval_seconds)


def start_erp_health_checker(interval_seconds: int = 20) -> None:
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
