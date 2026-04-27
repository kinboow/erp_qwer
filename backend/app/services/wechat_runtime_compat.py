import asyncio
import json
import logging
from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.services.downstream_orders import create_review_from_callback, resolve_customer_by_room
from app.services.message_logs import record_message_log
from app.services.at_order_handler import contains_order_keyword, extract_trigger_info, handle_at_order, is_at_bot

logger = logging.getLogger(__name__)


def _safe_text(value: Any) -> str:
    if value in (None, ""):
        return ""
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return str(value).strip()


def resolve_instance_id_by_wxid(db: Session, wxid: Optional[str]) -> Optional[str]:
    normalized_wxid = _safe_text(wxid)
    if not normalized_wxid:
        return None
    try:
        row = db.execute(
            text("SELECT id FROM wechat_instances WHERE wxid = :wxid LIMIT 1"),
            {"wxid": normalized_wxid},
        ).mappings().first()
        if row and row.get("id") is not None:
            return str(row.get("id"))
    except Exception:
        db.rollback()
    return None


def normalize_runtime_payload(payload: Any) -> dict[str, Any]:
    if isinstance(payload, dict):
        return payload
    if isinstance(payload, str):
        try:
            parsed = json.loads(payload)
            if isinstance(parsed, dict):
                return parsed
            return {"raw": parsed}
        except Exception:
            return {"raw": payload}
    return {"raw": _safe_text(payload)}


def _extract_wxid_from_payload(payload: dict) -> str:
    """从 payload 中提取机器人 wxid，兼容多种格式"""
    # 顶层 wxid（NGCBotV3-QW 转发格式）
    wxid = _safe_text(payload.get("wxid"))
    if wxid:
        return wxid
    # 原始 API 格式: data.receiver 是机器人的 wxid
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    wxid = _safe_text(data.get("receiver"))
    if wxid:
        return wxid
    # 嵌套格式: message.data.receiver
    message = payload.get("message") if isinstance(payload.get("message"), dict) else {}
    message_data = message.get("data") if isinstance(message.get("data"), dict) else {}
    return _safe_text(message_data.get("receiver"))


async def ingest_runtime_message(
    db: Session,
    payload: Any,
    *,
    source: str,
    instance_id: Optional[str] = None,
    wxid: Optional[str] = None,
) -> dict[str, Any]:
    normalized_payload = normalize_runtime_payload(payload)

    # 如果调用方未传 wxid，尝试从 payload 自动提取
    effective_wxid = _safe_text(wxid) or _extract_wxid_from_payload(normalized_payload)
    resolved_instance_id = _safe_text(instance_id) or resolve_instance_id_by_wxid(db, effective_wxid) or ""

    if resolved_instance_id and not normalized_payload.get("instanceId"):
        normalized_payload["instanceId"] = resolved_instance_id
    if effective_wxid and not normalized_payload.get("wxid"):
        normalized_payload["wxid"] = effective_wxid

    log_result = None
    try:
        log_result = record_message_log(
            db,
            normalized_payload,
            source=source,
            instance_id=resolved_instance_id or effective_wxid,
        )
    except Exception as exc:
        logger.warning("record_message_log failed: %s", exc)
        try:
            db.rollback()
        except Exception:
            pass

    review_result = None
    try:
        review_result = await create_review_from_callback(db, normalized_payload, resolved_instance_id or None)
    except Exception as exc:
        logger.warning("create_review_from_callback failed: %s", exc)
        try:
            db.rollback()
        except Exception:
            pass

    # @机器人 自动接单检测
    at_order_triggered = False
    try:
        bot_wxid = effective_wxid or _safe_text(normalized_payload.get("wxid"))
        if bot_wxid and is_at_bot(normalized_payload, bot_wxid):
            trigger_info = extract_trigger_info(normalized_payload, resolved_instance_id)
            trigger_room_id = trigger_info.get("room_id") or ""
            trigger_sender_id = trigger_info.get("sender_id") or ""
            trigger_content = trigger_info.get("content") or ""
            if trigger_room_id and trigger_sender_id and contains_order_keyword(trigger_content):
                customer = resolve_customer_by_room(db, trigger_room_id, resolved_instance_id)
                if customer:
                    trigger_msg_id = (log_result or {}).get("id") or 0
                    asyncio.create_task(handle_at_order(
                        room_id=trigger_room_id,
                        sender_id=trigger_sender_id,
                        customer=dict(customer),
                        trigger_msg_id=trigger_msg_id,
                        instance_id=trigger_info.get("instance_id") or "",
                    ))
                    at_order_triggered = True
                    logger.info("@接单: 已触发 room=%s sender=%s customer=%s",
                                trigger_room_id, trigger_sender_id, customer.get("customer_name"))
    except Exception as exc:
        logger.warning("@接单检测异常: %s", exc)

    return {
        "instanceId": resolved_instance_id,
        "wxid": effective_wxid or _safe_text(normalized_payload.get("wxid")),
        "received": True,
        "log": log_result,
        "review": review_result,
        "at_order_triggered": at_order_triggered,
    }
