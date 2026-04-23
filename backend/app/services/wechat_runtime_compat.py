import json
import logging
from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.services.downstream_orders import create_review_from_callback
from app.services.message_logs import record_message_log

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

    return {
        "instanceId": resolved_instance_id,
        "wxid": effective_wxid or _safe_text(normalized_payload.get("wxid")),
        "received": True,
        "log": log_result,
        "review": review_result,
    }
