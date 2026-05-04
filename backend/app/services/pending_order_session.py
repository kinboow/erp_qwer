"""
挂起报货会话管理
当客户发送的报货信息不完整（缺少款号/颜色/尺码/数量中的某些字段）时，
创建一个挂起会话，持续监听该群后续消息，直到信息补全后再走正常审核链。
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.services.downstream_support import ensure_downstream_support_tables

logger = logging.getLogger(__name__)

# 挂起会话默认超时时间（分钟）
SESSION_TIMEOUT_MINUTES = 30


def _session_key(room_id: str, sender_id: str) -> str:
    return f"{room_id}:{sender_id}"


def _json_dumps(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False)


def _json_loads(val: Any, default: Any = None):
    if val is None:
        return default
    if isinstance(val, (dict, list)):
        return val
    try:
        return json.loads(val)
    except Exception:
        return default


def _build_original_summary(context_messages: list[dict[str, Any]]) -> str:
    """从 context_messages 中提取纯文本摘要，供补全智能体使用。"""
    parts: list[str] = []
    for msg in context_messages:
        msg_type = msg.get("type", "text")
        if msg_type == "text":
            parts.append(msg.get("content") or "")
        elif msg_type == "image":
            parts.append("[图片]")
        elif msg_type == "file":
            fname = msg.get("file_name") or "附件"
            summary = msg.get("excel_summary") or msg.get("content") or ""
            parts.append(f"[文件:{fname}] {summary[:200]}")
    return "\n".join(parts)[:2000]


# ---------------------------------------------------------------------------
# CRUD 操作
# ---------------------------------------------------------------------------

def find_active_session(db: Session, room_id: str, sender_id: str) -> Optional[dict[str, Any]]:
    """查找该 room+sender 的活跃挂起会话（status=waiting 且未过期）。"""
    ensure_downstream_support_tables(db)
    row = db.execute(
        text(
            "SELECT * FROM pending_order_sessions "
            "WHERE session_key = :key AND status = 'waiting' AND expires_at > NOW() "
            "ORDER BY id DESC LIMIT 1"
        ),
        {"key": _session_key(room_id, sender_id)},
    ).mappings().first()
    if not row:
        return None
    return dict(row)


def find_any_active_session_in_room(db: Session, room_id: str) -> Optional[dict[str, Any]]:
    """查找该群内任意活跃的挂起会话。用于判断是否需要拦截消息。"""
    ensure_downstream_support_tables(db)
    row = db.execute(
        text(
            "SELECT * FROM pending_order_sessions "
            "WHERE room_id = :room_id AND status = 'waiting' AND expires_at > NOW() "
            "ORDER BY id DESC LIMIT 1"
        ),
        {"room_id": room_id},
    ).mappings().first()
    if not row:
        return None
    return dict(row)


def create_pending_session(
    db: Session,
    room_id: str,
    sender_id: str,
    instance_id: str,
    customer_id: Optional[int],
    customer_name: str,
    missing_fields: list[str],
    context_messages: list[dict[str, Any]],
    original_payload: dict[str, Any],
    ai_reason: str = "",
    timeout_minutes: int = SESSION_TIMEOUT_MINUTES,
) -> dict[str, Any]:
    """创建一个挂起报货会话。如果同一 room+sender 已有 waiting 会话，先标记为 cancelled。"""
    ensure_downstream_support_tables(db)
    key = _session_key(room_id, sender_id)

    # 取消同一人旧的挂起会话
    db.execute(
        text(
            "UPDATE pending_order_sessions SET status = 'cancelled', updated_at = NOW() "
            "WHERE session_key = :key AND status = 'waiting'"
        ),
        {"key": key},
    )

    expires_at = datetime.now() + timedelta(minutes=timeout_minutes)
    result = db.execute(
        text(
            "INSERT INTO pending_order_sessions "
            "(session_key, room_id, sender_id, instance_id, customer_id, customer_name, "
            "missing_fields, original_context, original_payload, followup_messages, "
            "status, ai_reason, expires_at) "
            "VALUES (:key, :room_id, :sender_id, :instance_id, :customer_id, :customer_name, "
            ":missing_fields, :original_context, :original_payload, :followup_messages, "
            "'waiting', :ai_reason, :expires_at)"
        ),
        {
            "key": key,
            "room_id": room_id,
            "sender_id": sender_id,
            "instance_id": instance_id,
            "customer_id": customer_id,
            "customer_name": customer_name,
            "missing_fields": _json_dumps(missing_fields),
            "original_context": _json_dumps(context_messages),
            "original_payload": _json_dumps(original_payload),
            "followup_messages": _json_dumps([]),
            "ai_reason": (ai_reason or "")[:500],
            "expires_at": expires_at,
        },
    )
    db.commit()
    session_id = result.lastrowid
    logger.info(
        "[PendingSession] 创建挂起会话 id=%d room=%s sender=%s missing=%s expires=%s",
        session_id, room_id, sender_id, missing_fields, expires_at,
    )
    return {
        "id": session_id,
        "session_key": key,
        "room_id": room_id,
        "sender_id": sender_id,
        "missing_fields": missing_fields,
        "expires_at": str(expires_at),
    }


def append_followup_message(
    db: Session,
    session_id: int,
    message: dict[str, Any],
) -> list[dict[str, Any]]:
    """向挂起会话追加一条后续消息，返回更新后的全部后续消息列表。"""
    row = db.execute(
        text("SELECT followup_messages FROM pending_order_sessions WHERE id = :id"),
        {"id": session_id},
    ).mappings().first()
    if not row:
        return []
    existing = _json_loads(row["followup_messages"], [])
    existing.append(message)
    db.execute(
        text(
            "UPDATE pending_order_sessions SET followup_messages = :msgs, updated_at = NOW() "
            "WHERE id = :id"
        ),
        {"id": session_id, "msgs": _json_dumps(existing)},
    )
    db.commit()
    return existing


def update_session_missing_fields(
    db: Session,
    session_id: int,
    still_missing: list[str],
) -> None:
    """更新会话的剩余缺失字段。"""
    db.execute(
        text(
            "UPDATE pending_order_sessions SET missing_fields = :fields, updated_at = NOW() "
            "WHERE id = :id"
        ),
        {"id": session_id, "fields": _json_dumps(still_missing)},
    )
    db.commit()


def mark_session_completed(db: Session, session_id: int) -> None:
    """标记会话为已补全。"""
    db.execute(
        text(
            "UPDATE pending_order_sessions SET status = 'completed', updated_at = NOW() "
            "WHERE id = :id"
        ),
        {"id": session_id},
    )
    db.commit()
    logger.info("[PendingSession] 会话已补全 id=%d", session_id)


def mark_session_expired(db: Session, session_id: int) -> None:
    """标记会话为已过期。"""
    db.execute(
        text(
            "UPDATE pending_order_sessions SET status = 'expired', updated_at = NOW() "
            "WHERE id = :id"
        ),
        {"id": session_id},
    )
    db.commit()


def cleanup_expired_sessions(db: Session) -> int:
    """清理所有过期的 waiting 会话，返回清理数量。"""
    ensure_downstream_support_tables(db)
    result = db.execute(
        text(
            "UPDATE pending_order_sessions SET status = 'expired', updated_at = NOW() "
            "WHERE status = 'waiting' AND expires_at <= NOW()"
        ),
    )
    db.commit()
    count = result.rowcount or 0
    if count:
        logger.info("[PendingSession] 清理了 %d 个过期挂起会话", count)
    return count


def get_merged_context(session: dict[str, Any]) -> list[dict[str, Any]]:
    """将原始消息和所有后续消息合并为一个完整的 context_messages 列表。"""
    original = _json_loads(session.get("original_context"), [])
    followups = _json_loads(session.get("followup_messages"), [])
    return original + followups


def get_original_summary(session: dict[str, Any]) -> str:
    """从会话的原始 context 提取摘要。"""
    original = _json_loads(session.get("original_context"), [])
    return _build_original_summary(original)
