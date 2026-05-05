"""
AI 熔断器 — 连续错误后暂停 AI 调用，记录错误期间的消息供恢复时选择重处理
"""

import asyncio
import logging
from datetime import datetime
from typing import Any, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 熔断器状态（进程级单例）
# ---------------------------------------------------------------------------
MAX_CONSECUTIVE_ERRORS = 3  # 连续错误阈值

_state = {
    "tripped": False,           # True = AI 已暂停
    "consecutive_errors": 0,
    "last_error": None,         # 最近一次错误信息
    "last_error_at": None,      # ISO 时间戳
    "tripped_at": None,         # 熔断触发时间
    "total_errors_since_trip": 0,
}

# 熔断期间缓冲的消息 (room_id, msg_log_id, content_preview, sender_name, created_at)
_buffered_messages: list[dict[str, Any]] = []


# ---------------------------------------------------------------------------
# 公共 API
# ---------------------------------------------------------------------------
def is_tripped() -> bool:
    """AI 是否已被熔断"""
    return _state["tripped"]


def get_status() -> dict[str, Any]:
    """获取熔断器完整状态"""
    return {
        **_state,
        "buffered_message_count": len(_buffered_messages),
    }


def record_success() -> None:
    """AI 调用成功时重置连续错误计数"""
    _state["consecutive_errors"] = 0


async def record_error(error_msg: str) -> None:
    """AI 调用失败时记录错误，达到阈值触发熔断"""
    _state["consecutive_errors"] += 1
    _state["last_error"] = error_msg
    _state["last_error_at"] = datetime.now().isoformat()

    logger.warning("[AI熔断] 连续错误 %d/%d: %s",
                   _state["consecutive_errors"], MAX_CONSECUTIVE_ERRORS, error_msg)

    if _state["consecutive_errors"] >= MAX_CONSECUTIVE_ERRORS and not _state["tripped"]:
        await _trip(error_msg)


def buffer_message(msg_info: dict[str, Any]) -> None:
    """熔断期间缓冲一条消息"""
    entry: dict[str, Any] = {
        "room_id": msg_info.get("room_id", ""),
        "msg_log_id": msg_info.get("msg_log_id"),
        "sender_id": msg_info.get("sender_id", ""),
        "sender_name": msg_info.get("sender_name", ""),
        "content_preview": msg_info.get("content_preview", ""),
        "customer_name": msg_info.get("customer_name", ""),
        "message_type": msg_info.get("message_type", "text"),
        "created_at": msg_info.get("created_at") or datetime.now().isoformat(),
    }
    # 发货扫码专属字段
    if msg_info.get("message_type") == "shipping_scan":
        entry["record_id"] = msg_info.get("record_id")
        entry["order_no"] = msg_info.get("order_no", "")
        entry["paper_id"] = msg_info.get("paper_id", "")
    _buffered_messages.append(entry)
    logger.info("[AI熔断] 缓冲消息: room=%s sender=%s preview=%s",
                msg_info.get("room_id"), msg_info.get("sender_name"),
                (msg_info.get("content_preview") or "")[:50])


def get_buffered_messages() -> list[dict[str, Any]]:
    """获取熔断期间缓冲的消息列表"""
    return list(_buffered_messages)


def clear_buffered_messages() -> None:
    """清空缓冲消息"""
    _buffered_messages.clear()


async def try_recover() -> dict[str, Any]:
    """尝试恢复: 测试 AI 连接，成功则解除熔断"""
    from app.database import SessionLocal
    db = SessionLocal()
    try:
        from app.services.ai_chat_service import _load_ai_config
        cfg = _load_ai_config(db)
    finally:
        db.close()

    if not cfg.get("enabled"):
        return {"ok": False, "error": "AI 已关闭，请先在配置中开启"}

    # 发一条简单测试消息（不含 tools 以避免工具调用副作用）
    import httpx
    base_url = cfg["base_url"].rstrip("/")
    api_key = cfg["api_key"]
    model = cfg["model"]
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{base_url}/chat/completions",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": "Say OK"}],
                    "temperature": 0,
                    "max_tokens": 16,
                },
            )
            resp.raise_for_status()
            result = resp.json()
        choice = (result.get("choices") or [{}])[0]
        content = (choice.get("message") or {}).get("content") or ""
        if not content:
            return {"ok": False, "error": "AI 返回空响应"}
    except Exception as exc:
        return {"ok": False, "error": f"AI 测试失败: {exc}"}

    # 测试通过，解除熔断
    _state["tripped"] = False
    _state["consecutive_errors"] = 0
    _state["last_error"] = None
    _state["last_error_at"] = None
    _state["tripped_at"] = None
    _state["total_errors_since_trip"] = 0

    logger.info("[AI熔断] 已恢复，缓冲消息 %d 条待用户选择重处理", len(_buffered_messages))

    # 通知前端
    try:
        from app.services import ws_notify
        await ws_notify.broadcast("ai_recovered")
    except Exception:
        pass

    # 通知群
    try:
        from app.services.notify_group import send_to_notification_groups
        await send_to_notification_groups(None, "✅ AI 服务已恢复正常")
    except Exception:
        pass

    return {
        "ok": True,
        "buffered_count": len(_buffered_messages),
    }


# ---------------------------------------------------------------------------
# 内部
# ---------------------------------------------------------------------------
async def _trip(error_msg: str) -> None:
    """触发熔断"""
    _state["tripped"] = True
    _state["tripped_at"] = datetime.now().isoformat()
    _state["total_errors_since_trip"] = _state["consecutive_errors"]

    logger.error("[AI熔断] 已触发！连续 %d 次错误，暂停 AI 调用", MAX_CONSECUTIVE_ERRORS)

    # 通知前端
    try:
        from app.services import ws_notify
        await ws_notify.broadcast("ai_tripped", {"error": error_msg})
    except Exception:
        pass

    # 系统消息
    try:
        from app.services.system_messages import create_system_message_background
        create_system_message_background(
            title="AI 服务异常已暂停",
            content=f"AI 连续 {MAX_CONSECUTIVE_ERRORS} 次调用失败，已自动暂停。\n错误：{error_msg}\n请在三方配置 > AI 模型配置中检查并恢复。",
            level="error",
            source="ai_circuit_breaker",
        )
    except Exception:
        pass

    # 通知群: 连发 2 条
    try:
        from app.services.notify_group import send_to_notification_groups
        await send_to_notification_groups(
            None,
            f"🔴 AI 服务异常！连续 {MAX_CONSECUTIVE_ERRORS} 次调用失败，已自动暂停。\n"
            f"错误：{error_msg}\n"
            f"期间收到的客户消息将被缓存，待恢复后可选择重新处理。"
        )
        await send_to_notification_groups(
            None,
            "⚠️ 请尽快前往系统管理 → 三方配置 → AI 模型配置 检查并恢复 AI 服务！"
        )
    except Exception:
        pass
