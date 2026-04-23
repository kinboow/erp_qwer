import json
from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.services.downstream_orders import create_review_from_callback
from app.services.message_logs import record_message_log


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
    row = db.execute(
        text("SELECT id FROM wechat_instances WHERE wxid = :wxid LIMIT 1"),
        {"wxid": normalized_wxid},
    ).mappings().first()
    if row and row.get("id") is not None:
        return str(row.get("id"))
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


async def ingest_runtime_message(
    db: Session,
    payload: Any,
    *,
    source: str,
    instance_id: Optional[str] = None,
    wxid: Optional[str] = None,
) -> dict[str, Any]:
    normalized_payload = normalize_runtime_payload(payload)
    resolved_instance_id = _safe_text(instance_id) or resolve_instance_id_by_wxid(db, wxid) or ""

    if resolved_instance_id and not normalized_payload.get("instanceId"):
        normalized_payload["instanceId"] = resolved_instance_id
    if wxid and not normalized_payload.get("wxid"):
        normalized_payload["wxid"] = _safe_text(wxid)

    record_message_log(
        db,
        normalized_payload,
        source=source,
        instance_id=resolved_instance_id or _safe_text(wxid),
    )
    created = await create_review_from_callback(db, normalized_payload, resolved_instance_id or None)
    return {
        "instanceId": resolved_instance_id,
        "wxid": _safe_text(wxid) or _safe_text(normalized_payload.get("wxid")),
        "received": True,
        "review": created,
    }
