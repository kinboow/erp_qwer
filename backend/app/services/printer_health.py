import asyncio
import logging
from datetime import datetime
from typing import Any

from app.services.printer_service import get_client_status, get_client_status_by_hostname

logger = logging.getLogger(__name__)

_poll_task: asyncio.Task | None = None
_check_lock = asyncio.Lock()
_status: dict[str, Any] = {
    "online": False,
    "last_checked_at": None,
    "last_error": "尚未检测",
    "hostname": "",
    "printer_name": "",
}
_prev_online: bool | None = None
_prev_host: str = ""


def _get_target_client_hostname() -> str:
    """从 printer_config 表读取配置的目标打印客户端 hostname。"""
    try:
        from app.database import SessionLocal
        from sqlalchemy import text as sa_text
        db = SessionLocal()
        try:
            row = db.execute(
                sa_text("SELECT config_value FROM printer_config WHERE config_key = 'printer_target_client' LIMIT 1")
            ).scalar()
            return str(row).strip() if row else ""
        finally:
            db.close()
    except Exception:
        return ""


async def _check_once() -> None:
    target_host = _get_target_client_hostname()

    if target_host:
        client = get_client_status_by_hostname(target_host)
    else:
        client = get_client_status()

    online = bool(client.get("online", False))
    hostname = str(client.get("hostname") or "")
    printer_name = str(client.get("printer_name") or "")
    seconds_ago = client.get("seconds_ago")

    if online:
        _status.update({
            "online": True,
            "hostname": hostname,
            "printer_name": printer_name,
            "last_checked_at": datetime.now().isoformat(),
            "last_error": None,
        })
        return

    if not target_host:
        _status.update({
            "online": False,
            "hostname": "",
            "printer_name": "",
            "last_checked_at": datetime.now().isoformat(),
            "last_error": "未配置目标打印客户端，跳过离线检测",
        })
        return

    error_msg = f"打印端 {target_host} 心跳超时"
    if seconds_ago is not None:
        error_msg += f"（距上次心跳 {seconds_ago} 秒）"

    _status.update({
        "online": False,
        "hostname": target_host,
        "printer_name": printer_name,
        "last_checked_at": datetime.now().isoformat(),
        "last_error": error_msg,
    })


async def refresh_printer_health_status() -> dict[str, Any]:
    global _prev_online, _prev_host
    async with _check_lock:
        await _check_once()
        current_online = bool(_status.get("online", False))
        current_host = str(_status.get("hostname") or "")
        current_printer = str(_status.get("printer_name") or "")

        if _prev_online is not None and _prev_online and not current_online:
            error_msg = _status.get("last_error") or "未知原因"
            try:
                from app.services.system_messages import create_system_message_background
                create_system_message_background(
                    title="打印端连接离线",
                    content=f"打印端连接检测失败：{error_msg}",
                    level="error",
                    source="printer_health",
                )
            except Exception:
                pass
            try:
                from app.services.notify_group import send_to_notification_groups
                await send_to_notification_groups(None, f"🔴 打印端离线\n原因：{error_msg}\n请尽快检查打印客户端是否在线。")
            except Exception:
                pass
            try:
                from app.services import ws_notify
                await ws_notify.broadcast("printer_offline", {"error": error_msg})
            except Exception:
                pass

        if _prev_online is not None and not _prev_online and current_online:
            detail = current_host or "未知主机"
            if current_printer:
                detail = f"{detail} / {current_printer}"
            try:
                from app.services.system_messages import create_system_message_background
                create_system_message_background(
                    title="打印端连接已恢复",
                    content=f"打印端已恢复在线，当前客户端：{detail}",
                    level="info",
                    source="printer_health",
                )
            except Exception:
                pass
            try:
                from app.services.notify_group import send_to_notification_groups
                await send_to_notification_groups(None, f"✅ 打印端已恢复在线\n当前客户端：{detail}")
            except Exception:
                pass
            try:
                from app.services import ws_notify
                await ws_notify.broadcast("printer_online", {"hostname": current_host, "printer_name": current_printer})
            except Exception:
                pass

        _prev_online = current_online
        _prev_host = current_host
        return get_printer_health_status()


async def _poll_loop(interval_seconds: int) -> None:
    while True:
        await refresh_printer_health_status()
        await asyncio.sleep(interval_seconds)


def start_printer_health_checker(interval_seconds: int = 10) -> None:
    global _poll_task
    if _poll_task and not _poll_task.done():
        return
    _poll_task = asyncio.create_task(_poll_loop(interval_seconds))
    logger.info("[Printer Health] 已启动健康检查轮询，间隔 %s 秒", interval_seconds)


def stop_printer_health_checker() -> None:
    global _poll_task
    if _poll_task and not _poll_task.done():
        _poll_task.cancel()
    _poll_task = None


def get_printer_health_status() -> dict[str, Any]:
    return {
        "online": bool(_status.get("online", False)),
        "hostname": _status.get("hostname") or "",
        "printer_name": _status.get("printer_name") or "",
        "last_checked_at": _status.get("last_checked_at"),
        "last_error": _status.get("last_error"),
        "polling": _poll_task is not None and not _poll_task.done() if _poll_task else False,
    }
