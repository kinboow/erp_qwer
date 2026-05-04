import json
import uuid
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database import SessionLocal


def _fmt_row(row) -> dict:
    item = dict(row)
    for k, v in item.items():
        if isinstance(v, datetime):
            item[k] = v.strftime("%Y-%m-%d %H:%M:%S")
    return item


MESSAGE_LOG_PREVIEW_LIMIT = 500


_msg_logs_table_ensured = False


def ensure_message_logs_table(db: Session):
    global _msg_logs_table_ensured
    if _msg_logs_table_ensured:
        return
    db.execute(text(
        "CREATE TABLE IF NOT EXISTS message_logs ("
        "id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY, "
        "msg_uid VARCHAR(36) NOT NULL DEFAULT '', "
        "source VARCHAR(50) NOT NULL DEFAULT 'http_callback', "
        "instance_id VARCHAR(100) DEFAULT '', "
        "room_id VARCHAR(100) DEFAULT '', "
        "room_name VARCHAR(200) DEFAULT '', "
        "sender_id VARCHAR(100) DEFAULT '', "
        "sender_name VARCHAR(200) DEFAULT '', "
        "message_type VARCHAR(50) DEFAULT '', "
        "content_preview TEXT NULL, "
        "payload_json LONGTEXT NULL, "
        "ai_recognized TINYINT NOT NULL DEFAULT 0, "
        "is_at_bot TINYINT NOT NULL DEFAULT 0, "
        "created_at DATETIME DEFAULT CURRENT_TIMESTAMP, "
        "UNIQUE INDEX idx_msg_uid (msg_uid), "
        "INDEX idx_source (source), "
        "INDEX idx_instance_id (instance_id), "
        "INDEX idx_room_id (room_id), "
        "INDEX idx_message_type (message_type), "
        "INDEX idx_created_at (created_at)"
        ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4"
    ))
    # 兼容已有表：补充缺失字段
    for col_sql in (
        "ALTER TABLE message_logs ADD COLUMN msg_uid VARCHAR(36) NOT NULL DEFAULT '' AFTER id",
        "ALTER TABLE message_logs ADD UNIQUE INDEX idx_msg_uid (msg_uid)",
        "ALTER TABLE message_logs ADD COLUMN ai_recognized TINYINT NOT NULL DEFAULT 0 AFTER payload_json",
        "ALTER TABLE message_logs ADD COLUMN is_at_bot TINYINT NOT NULL DEFAULT 0 AFTER ai_recognized",
        "ALTER TABLE message_logs ADD COLUMN oss_key VARCHAR(500) DEFAULT '' AFTER is_at_bot",
        "ALTER TABLE message_logs ADD COLUMN rescan_count TINYINT NOT NULL DEFAULT 0 AFTER oss_key",
        "ALTER TABLE message_logs ADD COLUMN message_server_id VARCHAR(100) DEFAULT '' AFTER rescan_count",
        "ALTER TABLE message_logs ADD COLUMN is_recalled TINYINT NOT NULL DEFAULT 0 AFTER message_server_id",
        "ALTER TABLE message_logs ADD INDEX idx_message_server_id (message_server_id)",
    ):
        try:
            db.execute(text(col_sql))
        except Exception:
            pass
    db.commit()
    _msg_logs_table_ensured = True


def _json_dumps(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False)


def _json_loads(data: Any, default: Any):
    if not data:
        return default
    if isinstance(data, (dict, list)):
        return data
    try:
        return json.loads(data)
    except Exception:
        return default


def _safe_text(value: Any) -> str:
    if value in (None, ""):
        return ""
    if isinstance(value, (dict, list)):
        return _json_dumps(value)
    return str(value).strip()


def _find_first(data: Any, keys: list[str]) -> Any:
    if isinstance(data, dict):
        lowered = {str(key).lower(): value for key, value in data.items()}
        for key in keys:
            value = lowered.get(key.lower())
            if value not in (None, ""):
                return value
        for value in data.values():
            found = _find_first(value, keys)
            if found not in (None, ""):
                return found
    elif isinstance(data, list):
        for item in data:
            found = _find_first(item, keys)
            if found not in (None, ""):
                return found
    return None


def _infer_message_type(payload: dict[str, Any]) -> str:
    message = payload.get("message") if isinstance(payload.get("message"), dict) else {}
    message_data = message.get("data") if isinstance(message.get("data"), dict) else {}
    if not message_data and isinstance(payload.get("data"), dict) and payload.get("type"):
        message_data = payload["data"]
    event_type = _safe_text(message.get("type") or payload.get("type") or payload.get("message_type"))
    content_type = _safe_text(message_data.get("content_type") or message_data.get("wx_type") or payload.get("content_type"))
    attachment_name = _safe_text(_find_first(payload, ["file_name", "filename", "name", "title"]))
    attachment_mime = _safe_text(_find_first(payload, ["mime_type", "mimetype", "content_type", "contenttype"]))
    text_content = _safe_text(_find_first(payload, ["content", "text", "msg", "message", "text_content"]))

    if event_type == "11041" or content_type == "2":
        return "text"
    if event_type == "11042" or content_type == "101":
        return "image"
    if event_type == "11045" or content_type == "102":
        return "file"
    if attachment_mime.startswith("image/"):
        return "image"
    if attachment_name.lower().endswith((".xlsx", ".xls", ".csv", ".pdf", ".txt", ".doc", ".docx")):
        return "file"
    if text_content:
        return "text"
    return _safe_text(_find_first(payload, ["message_type", "msg_type", "type"])) or "unknown"


def _extract_log_item(payload: Any, source: str, instance_id: Optional[str] = None) -> dict[str, Any]:
    normalized_payload = payload if isinstance(payload, dict) else {"raw": _safe_text(payload)}
    message = normalized_payload.get("message") if isinstance(normalized_payload.get("message"), dict) else {}
    message_data = message.get("data") if isinstance(message.get("data"), dict) else {}
    if not message_data and isinstance(normalized_payload.get("data"), dict) and normalized_payload.get("type"):
        message_data = normalized_payload["data"]

    sender_id = _safe_text(
        message_data.get("sender")
        or message_data.get("from_wxid")
        or normalized_payload.get("sender_id")
        or normalized_payload.get("from_wxid")
        or normalized_payload.get("sender")
    )
    sender_name = _safe_text(
        message_data.get("sender_name")
        or message_data.get("from_name")
        or normalized_payload.get("sender_name")
        or normalized_payload.get("nickname")
    )
    room_id = _safe_text(
        message_data.get("room_wxid")
        or message_data.get("room_conversation_id")
        or normalized_payload.get("room_id")
        or normalized_payload.get("conversation_id")
        or message_data.get("conversation_id")
    )
    room_name = _safe_text(
        message_data.get("room_name")
        or message_data.get("conversation_name")
        or normalized_payload.get("room_name")
    )
    content_preview = _safe_text(
        message_data.get("content")
        or message_data.get("text_content")
        or message_data.get("msg")
        or normalized_payload.get("content")
        or normalized_payload.get("msg")
        or normalized_payload.get("text")
        or _find_first(normalized_payload, ["file_name", "filename", "name", "title"])
    )
    if len(content_preview) > MESSAGE_LOG_PREVIEW_LIMIT:
        content_preview = f"{content_preview[:MESSAGE_LOG_PREVIEW_LIMIT]}..."

    inferred_instance_id = _safe_text(instance_id or normalized_payload.get("instanceId") or normalized_payload.get("instance_id") or normalized_payload.get("wxid"))
    # 提取 message_server_id（用于撤回消息匹配）
    msg_server_id = _safe_text(
        message_data.get("message_server_id")
        or message_data.get("server_id")
        or message_data.get("svr_id")
        or normalized_payload.get("message_server_id")
        or ""
    )
    return {
        "source": source,
        "instance_id": inferred_instance_id,
        "room_id": room_id,
        "room_name": room_name,
        "sender_id": sender_id,
        "sender_name": sender_name,
        "message_type": _infer_message_type(normalized_payload),
        "content_preview": content_preview,
        "payload_json": _json_dumps(normalized_payload),
        "message_server_id": msg_server_id,
    }


def record_message_log(db: Session, payload: Any, *, source: str, instance_id: Optional[str] = None) -> dict[str, Any]:
    ensure_message_logs_table(db)
    item = _extract_log_item(payload, source, instance_id)
    item["msg_uid"] = str(uuid.uuid4())
    result = db.execute(
        text(
            "INSERT INTO message_logs ("
            "msg_uid, source, instance_id, room_id, room_name, sender_id, sender_name, message_type, content_preview, payload_json, message_server_id"
            ") VALUES ("
            ":msg_uid, :source, :instance_id, :room_id, :room_name, :sender_id, :sender_name, :message_type, :content_preview, :payload_json, :message_server_id"
            ")"
        ),
        item,
    )
    db.commit()
    item["id"] = result.lastrowid
    return item


def record_message_log_background(payload: Any, *, source: str, instance_id: Optional[str] = None):
    db = SessionLocal()
    try:
        record_message_log(db, payload, source=source, instance_id=instance_id)
    finally:
        db.close()


def mark_recalled(db: Session, message_server_id: str, room_id: str = "") -> int:
    """根据 message_server_id 标记消息为已撤回，返回被标记的 message_log id（0 表示未找到）"""
    if not message_server_id:
        return 0
    try:
        conditions = "message_server_id = :sid AND is_recalled = 0"
        params: dict[str, Any] = {"sid": message_server_id}
        if room_id:
            clean_rid = room_id[2:] if room_id.startswith("R:") else room_id
            conditions += " AND room_id IN (:rid1, :rid2)"
            params["rid1"] = room_id
            params["rid2"] = clean_rid
        row = db.execute(
            text(f"SELECT id FROM message_logs WHERE {conditions} ORDER BY id DESC LIMIT 1"),
            params,
        ).first()
        if not row:
            return 0
        msg_id = row[0]
        db.execute(
            text("UPDATE message_logs SET is_recalled = 1, ai_recognized = 1 WHERE id = :id"),
            {"id": msg_id},
        )
        db.commit()
        return msg_id
    except Exception:
        return 0


def mark_ai_recognized(db: Session, msg_log_id: int, recognized: bool = True) -> None:
    """标记消息已被 AI 识别处理"""
    try:
        db.execute(
            text("UPDATE message_logs SET ai_recognized = :val WHERE id = :id"),
            {"val": 1 if recognized else 0, "id": msg_log_id},
        )
        db.commit()
    except Exception:
        pass


def increment_rescan_count(db: Session, msg_log_id: int) -> int:
    """递增补扫重试次数，返回递增后的值"""
    try:
        db.execute(
            text("UPDATE message_logs SET rescan_count = rescan_count + 1 WHERE id = :id"),
            {"id": msg_log_id},
        )
        db.commit()
        row = db.execute(
            text("SELECT rescan_count FROM message_logs WHERE id = :id"),
            {"id": msg_log_id},
        ).first()
        return row[0] if row else 0
    except Exception:
        return 0


def get_unrecognized_media_messages(db: Session, limit: int = 15) -> list[dict[str, Any]]:
    """获取最近 N 条未被 AI 识别的图片/文件消息，用于启动时补扫。"""
    ensure_message_logs_table(db)
    rows = db.execute(
        text(
            "SELECT id, msg_uid, source, instance_id, room_id, room_name, sender_id, sender_name, "
            "message_type, content_preview, payload_json, ai_recognized, created_at "
            "FROM message_logs "
            "WHERE message_type IN ('image', 'file') AND ai_recognized = 0 AND is_recalled = 0 "
            "ORDER BY id DESC LIMIT :limit"
        ),
        {"limit": limit},
    ).mappings().all()
    return [_fmt_row(r) for r in rows]


def get_unrecognized_at_messages(db: Session, limit: int = 15) -> list[dict[str, Any]]:
    """获取最近 N 条未被 AI 识别的 @bot 消息，用于启动时补扫。"""
    ensure_message_logs_table(db)
    rows = db.execute(
        text(
            "SELECT id, msg_uid, source, instance_id, room_id, room_name, sender_id, sender_name, "
            "message_type, content_preview, payload_json, ai_recognized, is_at_bot, created_at "
            "FROM message_logs "
            "WHERE is_at_bot = 1 AND ai_recognized = 0 AND is_recalled = 0 "
            "ORDER BY id DESC LIMIT :limit"
        ),
        {"limit": limit},
    ).mappings().all()
    return [_fmt_row(r) for r in rows]


def list_message_logs(
    db: Session,
    *,
    page: int = 1,
    page_size: int = 20,
    source: str = "",
    message_type: str = "",
    keyword: str = "",
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> dict[str, Any]:
    ensure_message_logs_table(db)
    conditions = ["1 = 1"]
    params: dict[str, Any] = {"limit": page_size, "offset": (page - 1) * page_size}
    if source:
        conditions.append("source = :source")
        params["source"] = source
    if message_type:
        conditions.append("message_type = :message_type")
        params["message_type"] = message_type
    if keyword:
        conditions.append("(content_preview LIKE :keyword OR room_name LIKE :keyword OR sender_name LIKE :keyword OR payload_json LIKE :keyword)")
        params["keyword"] = f"%{keyword}%"
    if start_date:
        conditions.append("created_at >= :start_date")
        params["start_date"] = f"{start_date} 00:00:00"
    if end_date:
        conditions.append("created_at <= :end_date")
        params["end_date"] = f"{end_date} 23:59:59"
    where_sql = " AND ".join(conditions)
    rows = db.execute(
        text(f"SELECT id, msg_uid, source, instance_id, room_id, room_name, sender_id, sender_name, message_type, content_preview, payload_json, ai_recognized, is_at_bot, is_recalled, created_at FROM message_logs WHERE {where_sql} ORDER BY created_at DESC LIMIT :limit OFFSET :offset"),
        params,
    ).mappings().all()
    count_params = {key: value for key, value in params.items() if key not in {"limit", "offset"}}
    total = db.execute(text(f"SELECT COUNT(*) AS total FROM message_logs WHERE {where_sql}"), count_params).mappings().first()["total"]
    result = []
    for row in rows:
        item = _fmt_row(row)
        item["payload"] = _json_loads(item.get("payload_json"), {})
        item.pop("payload_json", None)
        result.append(item)
    return {
        "list": result,
        "total": total,
        "page": page,
        "pageSize": page_size,
    }
