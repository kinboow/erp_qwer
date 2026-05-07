import asyncio
import logging
from datetime import datetime
from typing import Any

import httpx

from app.database import SessionLocal
from app.services.ai_config import get_ai_config_for_parser

logger = logging.getLogger(__name__)

_poll_task: asyncio.Task | None = None
_check_lock = asyncio.Lock()
_status: dict[str, Any] = {
    "online": False,
    "last_checked_at": None,
    "last_error": "尚未检测",
    "provider": "",
    "model": "",
}
_prev_online: bool | None = None


async def _check_once() -> None:
    db = SessionLocal()
    try:
        cfg = get_ai_config_for_parser(db)
    finally:
        db.close()

    provider = str(cfg.get("provider") or "")
    model = str(cfg.get("model") or "")
    enabled = bool(cfg.get("enabled"))
    base_url = str(cfg.get("base_url") or "").strip().rstrip("/")
    api_key = str(cfg.get("api_key") or "").strip()

    if not enabled:
        _status.update({
            "online": False,
            "provider": provider,
            "model": model,
            "last_checked_at": datetime.now().isoformat(),
            "last_error": "AI 服务未启用",
        })
        return

    if not base_url or not model or not api_key:
        _status.update({
            "online": False,
            "provider": provider,
            "model": model,
            "last_checked_at": datetime.now().isoformat(),
            "last_error": "AI 配置不完整",
        })
        return

    try:
        async with httpx.AsyncClient(timeout=20.0, trust_env=False) as client:
            resp = await client.post(
                f"{base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": "请回复OK"}],
                    "temperature": 0,
                    "max_tokens": 16,
                },
            )
            resp.raise_for_status()
            data = resp.json()
        reply = (((data.get("choices") or [{}])[0].get("message") or {}).get("content") or "").strip()
        if not reply:
            raise RuntimeError("AI 返回空响应")
        _status.update({
            "online": True,
            "provider": provider,
            "model": model,
            "last_checked_at": datetime.now().isoformat(),
            "last_error": None,
        })
    except Exception as exc:
        _status.update({
            "online": False,
            "provider": provider,
            "model": model,
            "last_checked_at": datetime.now().isoformat(),
            "last_error": str(exc),
        })


async def refresh_ai_health_status() -> dict[str, Any]:
    global _prev_online
    async with _check_lock:
        await _check_once()
        current_online = bool(_status.get("online", False))
        provider = _status.get("provider") or "AI"
        model = _status.get("model") or ""

        if _prev_online is not None and _prev_online and not current_online:
            error_msg = _status.get("last_error") or "未知原因"
            try:
                from app.services.system_messages import create_system_message_background
                create_system_message_background(
                    title="AI 服务离线",
                    content=f"AI 服务连接检测失败：{error_msg}",
                    level="error",
                    source="ai_health",
                )
            except Exception:
                pass
            try:
                from app.services.notify_group import send_to_notification_groups
                await send_to_notification_groups(None, f"🔴 AI服务离线\n模型：{model or '未配置'}\n原因：{error_msg}\n请尽快检查 AI 服务状态。")
            except Exception:
                pass
            try:
                from app.services import ws_notify
                await ws_notify.broadcast("ai_offline", {"error": error_msg})
            except Exception:
                pass

        if _prev_online is not None and not _prev_online and current_online:
            try:
                from app.services.system_messages import create_system_message_background
                create_system_message_background(
                    title="AI 服务已恢复",
                    content=f"AI 服务已恢复正常，provider={provider}，model={model or '未配置'}",
                    level="info",
                    source="ai_health",
                )
            except Exception:
                pass
            try:
                from app.services.notify_group import send_to_notification_groups
                await send_to_notification_groups(None, f"✅ AI服务已恢复\nProvider：{provider}\n模型：{model or '未配置'}")
            except Exception:
                pass
            try:
                from app.services import ws_notify
                await ws_notify.broadcast("ai_online", {"provider": provider, "model": model})
            except Exception:
                pass

        _prev_online = current_online
        return get_ai_health_status()


async def _poll_loop(interval_seconds: int) -> None:
    while True:
        await refresh_ai_health_status()
        await asyncio.sleep(interval_seconds)


def start_ai_health_checker(interval_seconds: int = 30) -> None:
    global _poll_task
    if _poll_task and not _poll_task.done():
        return
    _poll_task = asyncio.create_task(_poll_loop(interval_seconds))
    logger.info("[AI Health] 已启动健康检查轮询，间隔 %s 秒", interval_seconds)


def stop_ai_health_checker() -> None:
    global _poll_task
    if _poll_task and not _poll_task.done():
        _poll_task.cancel()
    _poll_task = None


def get_ai_health_status() -> dict[str, Any]:
    return {
        "online": bool(_status.get("online", False)),
        "provider": _status.get("provider") or "",
        "model": _status.get("model") or "",
        "last_checked_at": _status.get("last_checked_at"),
        "last_error": _status.get("last_error"),
        "polling": _poll_task is not None and not _poll_task.done() if _poll_task else False,
    }
