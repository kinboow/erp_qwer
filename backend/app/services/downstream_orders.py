import base64
import io
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

import httpx
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database import SessionLocal, run_in_threadpool
from app.models import User, WechatInstance
from app.services.ai_order_parser import AIOrderParserError, ai_order_parser
from app.services.downstream_support import ensure_downstream_support_tables
from app.services.erp_bridge import ERPBridge, ERPBridgeError
from app.services.wechat_event_types import EVENT_TYPE_TO_MESSAGE_TYPE, CONTENT_TYPE_TO_MESSAGE_TYPE

try:
    from openpyxl import load_workbook
except Exception:
    load_workbook = None


erp_bridge = ERPBridge()


class AttachmentContentRequiredError(Exception):
    pass


SUPPORTED_REVIEW_MESSAGE_TYPES = {"text", "image", "file"}


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


def _safe_text(value: Any) -> str:
    if value in (None, ""):
        return ""
    if isinstance(value, (dict, list)):
        return _json_dumps(value)
    return str(value).strip()


def _normalize_instance_id(value: Any) -> Optional[int]:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _guess_attachment_mime(file_name: str, current_mime: str, message_type: str) -> str:
    if current_mime:
        return current_mime
    normalized_name = (file_name or "").lower()
    mime_map = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".bmp": "image/bmp",
        ".webp": "image/webp",
        ".gif": "image/gif",
        ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ".xls": "application/vnd.ms-excel",
        ".csv": "text/csv",
        ".txt": "text/plain",
        ".pdf": "application/pdf",
    }
    for ext, mime in mime_map.items():
        if normalized_name.endswith(ext):
            return mime
    if message_type == "image":
        return "image/png"
    return ""


def _read_local_attachment_base64(file_reference: str) -> str:
    if not file_reference or file_reference.startswith("data:") or "://" in file_reference:
        return ""
    try:
        path = Path(file_reference)
    except Exception:
        return ""
    if not path.is_file():
        return ""
    try:
        return base64.b64encode(path.read_bytes()).decode("ascii")
    except Exception:
        return ""


def _build_wechat_api_base_url(host: str, port: str) -> str:
    normalized_host = (host or "").strip()
    normalized_port = (port or "").strip()
    if not normalized_host:
        return ""
    if normalized_host.startswith("http://") or normalized_host.startswith("https://"):
        return normalized_host.rstrip("/") if not normalized_port else f"{normalized_host.rstrip('/')}:{normalized_port}"
    base = f"http://{normalized_host}"
    if normalized_port:
        base = f"{base}:{normalized_port}"
    return base.rstrip("/")


def _build_wechat_headers(api_key: str) -> dict[str, str]:
    headers = {}
    if api_key:
        headers["X-API-Key"] = api_key
    return headers


def _guess_attachment_extension(attachment_name: str, attachment_mime: str, message_type: str) -> str:
    normalized_name = (attachment_name or "").lower()
    known_exts = [
        ".png", ".jpg", ".jpeg", ".bmp", ".webp", ".gif", ".xlsx", ".xls", ".csv", ".txt", ".pdf", ".doc", ".docx"
    ]
    for ext in known_exts:
        if normalized_name.endswith(ext):
            return ext
    mime_map = {
        "image/png": ".png",
        "image/jpeg": ".jpg",
        "image/bmp": ".bmp",
        "image/webp": ".webp",
        "image/gif": ".gif",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
        "application/vnd.ms-excel": ".xls",
        "text/csv": ".csv",
        "text/plain": ".txt",
        "application/pdf": ".pdf",
    }
    if attachment_mime in mime_map:
        return mime_map[attachment_mime]
    return ".png" if message_type == "image" else ".bin"


def _infer_c2c_file_type(message_type: str, attachment_name: str, attachment_mime: str) -> int:
    if message_type == "image" or (attachment_mime or "").startswith("image/"):
        return 2
    normalized_name = (attachment_name or "").lower()
    if normalized_name.endswith((".mp4", ".mov", ".avi", ".mkv")):
        return 4
    if normalized_name.endswith((".mp3", ".wav", ".aac", ".amr")):
        return 3
    return 5


def _extract_download_request_data(payload: dict[str, Any], row: dict[str, Any]) -> dict[str, Any]:
    message = payload.get("message") if isinstance(payload.get("message"), dict) else {}
    message_data = message.get("data") if isinstance(message.get("data"), dict) else {}
    cdn_payload = message_data.get("cdn") if isinstance(message_data.get("cdn"), dict) else {}
    c2c_payload = message_data.get("c2c_cdn") if isinstance(message_data.get("c2c_cdn"), dict) else {}

    url = _find_first({"payload": payload, "message": message_data, "cdn": cdn_payload}, ["url"])
    auth_key = _find_first({"payload": payload, "message": message_data, "cdn": cdn_payload}, ["auth_key", "authKey"])
    aes_key = _find_first({"payload": payload, "message": message_data, "cdn": cdn_payload, "c2c": c2c_payload}, ["aes_key", "aesKey"])
    file_id = _find_first({"payload": payload, "message": message_data, "cdn": cdn_payload, "c2c": c2c_payload}, ["file_id", "fileId"])
    size = _find_first({"payload": payload, "message": message_data, "cdn": cdn_payload, "c2c": c2c_payload}, ["size", "file_size", "fileSize"])
    try:
        size = int(size or 0)
    except Exception:
        size = 0

    if url and auth_key and aes_key and size:
        return {
            "mode": "wx_download",
            "url": str(url),
            "auth_key": str(auth_key),
            "aes_key": str(aes_key),
            "size": size,
        }

    if file_id and aes_key:
        return {
            "mode": "c2c_download",
            "file_id": str(file_id),
            "aes_key": str(aes_key),
            "file_size": size,
            "file_type": _infer_c2c_file_type(str(row.get("message_type") or ""), str(row.get("attachment_name") or ""), str(row.get("attachment_mime") or "")),
        }

    return {}


def _resolve_wechat_runtime_config(db: Session, row: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    instance_id = row.get("instance_id")
    instance = None
    if instance_id:
        instance = db.query(WechatInstance).filter(WechatInstance.id == instance_id).first()
    if instance:
        return {
            "api_base_url": instance.api_base_url.rstrip("/"),
            "api_key": instance.api_key or "",
            "wxid": instance.wxid,
        }

    try:
        config_row = db.execute(text("SELECT host, port, api_key, selected_wxid FROM wechat_config WHERE id = 1")).mappings().first()
    except Exception:
        config_row = None

    payload_wxid = _safe_text(payload.get("wxid") or _find_first(payload, ["wxid", "robot_id", "robotId"]))
    if config_row:
        return {
            "api_base_url": _build_wechat_api_base_url(config_row.get("host") or "", config_row.get("port") or ""),
            "api_key": config_row.get("api_key") or "",
            "wxid": config_row.get("selected_wxid") or payload_wxid,
        }

    return {"api_base_url": "", "api_key": "", "wxid": payload_wxid}


async def _download_review_attachment_content(db: Session, row: dict[str, Any]) -> dict[str, Any]:
    payload = _json_loads(row.get("callback_payload"), {})
    runtime = _resolve_wechat_runtime_config(db, row, payload)
    if not runtime.get("api_base_url") or not runtime.get("wxid"):
        raise AttachmentContentRequiredError("缺少企业微信实例配置，无法下载附件")

    download_request = _extract_download_request_data(payload, row)
    if not download_request:
        raise AttachmentContentRequiredError("回调中缺少可用的 CDN 下载参数，无法下载附件")

    extension = _guess_attachment_extension(str(row.get("attachment_name") or ""), str(row.get("attachment_mime") or ""), str(row.get("message_type") or ""))
    download_dir = Path(__file__).resolve().parents[2] / "temp" / "wechat_attachments"
    download_dir.mkdir(parents=True, exist_ok=True)
    save_path = download_dir / f"review_{row['id']}{extension}"

    api_route = "cdn/wx_download" if download_request.get("mode") == "wx_download" else "cdn/c2c_download"
    request_body = dict(download_request)
    request_body["save_path"] = str(save_path)
    request_body.pop("mode", None)

    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(
            f"{runtime['api_base_url']}/api/{runtime['wxid']}/{api_route}",
            json=request_body,
            headers=_build_wechat_headers(runtime.get("api_key") or ""),
        )
        response.raise_for_status()
        response_payload = response.json()

    if isinstance(response_payload, dict) and response_payload.get("code") not in (0, None):
        raise AttachmentContentRequiredError(response_payload.get("msg") or "企业微信附件下载失败")

    if not save_path.is_file():
        possible_path = _safe_text(_find_first(response_payload, ["save_path", "path", "file_path"]))
        if possible_path and Path(possible_path).is_file():
            save_path = Path(possible_path)
    if not save_path.is_file():
        raise AttachmentContentRequiredError("企业微信接口已返回成功，但未找到下载后的附件文件")

    file_bytes = save_path.read_bytes()
    attachment_base64 = base64.b64encode(file_bytes).decode("ascii")
    attachment_name = str(row.get("attachment_name") or save_path.name)
    attachment_mime = _guess_attachment_mime(attachment_name, str(row.get("attachment_mime") or ""), str(row.get("message_type") or ""))

    db.execute(
        text("UPDATE downstream_order_reviews SET attachment_name = :attachment_name, attachment_mime = :attachment_mime, attachment_base64 = :attachment_base64, parse_status = 'pending', ai_error = '', updated_at = NOW() WHERE id = :id"),
        {
            "id": row["id"],
            "attachment_name": attachment_name,
            "attachment_mime": attachment_mime,
            "attachment_base64": attachment_base64,
        },
    )
    db.commit()
    return {
        "attachment_name": attachment_name,
        "attachment_mime": attachment_mime,
        "save_path": str(save_path),
        "bytes": len(file_bytes),
    }


def _normalize_message_type(
    event_type: Any,
    content_type: Any,
    message_data: dict[str, Any],
    content_text: str,
    attachment_name: str,
    attachment_url: str,
    attachment_mime: str,
) -> str:
    event_key = _safe_text(event_type)
    if event_key.isdigit() and int(event_key) in EVENT_TYPE_TO_MESSAGE_TYPE:
        return EVENT_TYPE_TO_MESSAGE_TYPE[int(event_key)]

    content_key = _safe_text(content_type)
    if content_key.isdigit() and int(content_key) in CONTENT_TYPE_TO_MESSAGE_TYPE:
        return CONTENT_TYPE_TO_MESSAGE_TYPE[int(content_key)]

    if message_data.get("image") or attachment_mime.startswith("image/"):
        return "image"

    normalized_name = (attachment_name or attachment_url).lower()
    if normalized_name.endswith((".xlsx", ".xls", ".csv", ".txt", ".pdf", ".doc", ".docx", ".zip", ".rar", ".7z")):
        return "file"

    if any(message_data.get(key) for key in ["file_name", "file", "cdn", "c2c_cdn"]):
        return "file"

    if content_text:
        return "text"

    return _safe_text(message_data.get("message_type") or event_type or "unknown").lower() or "unknown"


def _extract_callback_message(payload: dict[str, Any], instance_id: Optional[str]) -> dict[str, Any]:
    payload = payload if isinstance(payload, dict) else {}

    # 兼容三种回调格式:
    # 1. NGCBotV3-QW 转发格式: { "message": { "type": ..., "data": {...} }, "wxid": "..." }
    # 2. 原始 API 格式:        { "type": 11041, "data": { "content": "...", ... } }
    # 3. NGCDemo legacy 格式:   { "message": { "type": ..., "data": { "msg": "...", "from_wxid": "..." } } }
    message = payload.get("message") if isinstance(payload.get("message"), dict) else {}
    message_data = message.get("data") if isinstance(message.get("data"), dict) else {}

    # 原始 API 格式: type 和 data 在顶层，没有 message 包裹
    if not message_data and isinstance(payload.get("data"), dict) and payload.get("type"):
        message_data = payload["data"]

    source_format = "generic"
    if message_data and any(key in message_data for key in ["conversation_id", "sender", "sender_name", "content_type"]):
        source_format = "ngcbot_v3"
    elif message_data and any(key in message_data for key in ["room_wxid", "from_wxid", "msg", "wx_type"]):
        source_format = "ngcdemo_legacy"

    normalized_instance_id = _normalize_instance_id(instance_id or payload.get("instanceId") or payload.get("instance_id"))
    event_type = message.get("type") or payload.get("type") or payload.get("message_type") or payload.get("msg_type")
    content_type = message_data.get("content_type") or payload.get("content_type") or message_data.get("wx_type")

    sender_id = _safe_text(
        message_data.get("sender")
        or message_data.get("from_wxid")
        or payload.get("sender_id")
        or payload.get("from_wxid")
        or payload.get("sender")
    )
    sender_name = _safe_text(
        message_data.get("sender_name")
        or message_data.get("from_name")
        or payload.get("sender_name")
        or payload.get("nickname")
    )

    room_id = _safe_text(
        message_data.get("room_wxid")
        or message_data.get("room_conversation_id")
        or payload.get("room_id")
        or payload.get("roomid")
    )
    conversation_id = _safe_text(message_data.get("conversation_id") or payload.get("conversation_id"))
    if not room_id and conversation_id and sender_id and conversation_id != sender_id:
        room_id = conversation_id

    room_name = _safe_text(
        message_data.get("room_name")
        or message_data.get("conversation_name")
        or payload.get("room_name")
        or payload.get("conversation_name")
    )

    content_text = _safe_text(
        message_data.get("content")
        or message_data.get("text_content")
        or message_data.get("msg")
        or payload.get("content")
        or payload.get("msg")
        or payload.get("text")
    )

    cdn_payload = message_data.get("cdn") if isinstance(message_data.get("cdn"), dict) else {}
    c2c_cdn_payload = message_data.get("c2c_cdn") if isinstance(message_data.get("c2c_cdn"), dict) else {}
    media_payload = cdn_payload or c2c_cdn_payload

    local_attachment_ref = _safe_text(
        message_data.get("image")
        or message_data.get("file")
        or message_data.get("video")
        or payload.get("file_path")
        or payload.get("image")
    )
    attachment_name = _safe_text(
        message_data.get("file_name")
        or media_payload.get("file_name")
        or payload.get("file_name")
        or payload.get("filename")
        or payload.get("name")
        or payload.get("title")
    )
    if local_attachment_ref and not attachment_name:
        try:
            attachment_name = Path(local_attachment_ref).name
        except Exception:
            attachment_name = ""

    attachment_url = _safe_text(
        payload.get("file_url")
        or payload.get("download_url")
        or payload.get("downloadUrl")
        or media_payload.get("url")
        or local_attachment_ref
    )
    attachment_mime = _safe_text(
        payload.get("mime_type")
        or payload.get("mimetype")
        or payload.get("content_type")
        or message_data.get("mime_type")
    )
    attachment_base64 = _safe_text(
        payload.get("file_base64")
        or payload.get("base64")
        or payload.get("data_base64")
        or message_data.get("file_base64")
    )

    if not attachment_base64 and local_attachment_ref:
        attachment_base64 = _read_local_attachment_base64(local_attachment_ref)

    if attachment_base64.startswith("data:"):
        header, encoded = attachment_base64.split(",", 1)
        attachment_base64 = encoded
        if not attachment_mime and ";base64" in header:
            attachment_mime = header.split(":", 1)[1].split(";", 1)[0]

    message_type = _normalize_message_type(
        event_type,
        content_type,
        message_data,
        content_text,
        attachment_name,
        attachment_url,
        attachment_mime,
    )
    attachment_mime = _guess_attachment_mime(attachment_name or attachment_url, attachment_mime, message_type)

    if not content_text and message_type in {"image", "file"}:
        prefix = "图片" if message_type == "image" else "文件"
        content_text = f"[{prefix}] {attachment_name or attachment_url or '附件消息'}"

    is_group_message = bool(room_id) and (room_id != sender_id or not sender_id)
    has_usable_content = bool(content_text or attachment_base64 or attachment_url or attachment_name)
    requires_attachment_download = message_type in {"image", "file"} and not attachment_base64 and bool(attachment_url or attachment_name)

    skip_reason = ""
    if not payload:
        skip_reason = "empty_payload"
    elif not is_group_message:
        skip_reason = "not_group_message"
    elif message_type not in SUPPORTED_REVIEW_MESSAGE_TYPES:
        skip_reason = f"unsupported_message_type:{message_type}"
    elif not has_usable_content:
        skip_reason = "empty_message_content"

    return {
        "source_type": f"wechat_{source_format}",
        "instance_id": normalized_instance_id,
        "room_id": room_id,
        "room_name": room_name,
        "sender_id": sender_id,
        "sender_name": sender_name,
        "message_type": message_type,
        "content_text": content_text,
        "attachment_name": attachment_name,
        "attachment_url": attachment_url,
        "attachment_mime": attachment_mime,
        "attachment_base64": attachment_base64,
        "event_type": _safe_text(event_type),
        "content_type": _safe_text(content_type),
        "source_format": source_format,
        "is_group_message": is_group_message,
        "requires_attachment_download": requires_attachment_download,
        "is_order_candidate": not skip_reason,
        "skip_reason": skip_reason,
    }


def _extract_excel_summary(attachment_base64: str) -> str:
    if not attachment_base64:
        return ""
    if load_workbook is None:
        return "Excel 文件已收到，但当前环境未安装 openpyxl。"
    try:
        binary = base64.b64decode(attachment_base64)
        workbook = load_workbook(io.BytesIO(binary), data_only=True)
    except Exception as exc:
        return f"Excel 解析失败: {exc}"

    lines: list[str] = []
    for sheet in workbook.worksheets[:3]:
        lines.append(f"[Sheet] {sheet.title}")
        for row in sheet.iter_rows(min_row=1, max_row=30, values_only=True):
            row_values = ["" if cell is None else str(cell).strip() for cell in row[:20]]
            if any(row_values):
                lines.append("\t".join(row_values))
    return "\n".join(lines[:240])


def _resolve_product_no_for_context(db: Session, name: str) -> str:
    """通过映射表或产品表解析 AI 提取的款号 → 真实货号。

    优先级：映射表 > 产品表精确匹配 > 原值
    这样即使 AI 提取的款号在产品表中存在，只要映射表里配了别名也会被正确映射。
    """
    name = name.strip()
    if not name:
        return name
    # 1. 优先查映射表——用户显式配置的别名拥有最高优先级
    try:
        alias = db.execute(
            text("SELECT product_no FROM product_name_mappings WHERE alias_name = :name LIMIT 1"),
            {"name": name},
        ).mappings().first()
        if alias:
            return alias["product_no"]
    except Exception:
        pass
    # 2. 精确匹配 erp_products
    direct = db.execute(
        text("SELECT product_no FROM erp_products WHERE product_no = :name LIMIT 1"),
        {"name": name},
    ).mappings().first()
    if direct:
        return direct["product_no"]
    return name


def query_product_context_for_nos(db: Session, product_nos: list[str]) -> str:
    """根据款号列表查询产品表中每个款号的可选颜色和尺码，返回格式化文本。

    流程：
    1. 先通过产品表精确匹配或映射表解析别名 → 真实货号
    2. 用真实货号查询 erp_products 获取可选颜色（color 字段）和尺码规格（spec 字段）
    """
    if not product_nos:
        return "未提取到款号，无法查询产品信息。"

    from app.services.erp_sync import ensure_tables
    ensure_tables(db)

    lines: list[str] = []
    for pno in product_nos:
        # 步骤1：解析真实货号（精确匹配 + 别名映射）
        resolved_pno = _resolve_product_no_for_context(db, pno)
        pno_label = f"{pno}（→{resolved_pno}）" if resolved_pno != pno else pno

        # 步骤2：从产品表查询颜色和尺码规格
        product_row = db.execute(
            text("SELECT color, spec FROM erp_products WHERE product_no = :pno LIMIT 1"),
            {"pno": resolved_pno},
        ).mappings().first()

        if not product_row:
            lines.append(f"款号 {pno_label}：产品表中未找到该货号")
            continue

        color_text = (product_row["color"] or "").strip()
        spec_text = (product_row["spec"] or "").strip()

        if color_text or spec_text:
            lines.append(f"款号 {pno_label} 可选信息：")
            if color_text:
                lines.append(f"  可选颜色：{color_text}")
            if spec_text:
                lines.append(f"  可选尺码：{spec_text}")
        else:
            lines.append(f"款号 {pno_label}：产品表中无颜色和尺码信息")

    return "\n".join(lines)


def query_product_context_structured(db: Session, product_nos: list[str]) -> dict[str, Any]:
    """根据款号列表查询产品表，返回结构化的可选尺码、颜色和款号映射。

    返回:
        {
            "sizes": ["M", "L", "XL", ...],
            "colors": ["黑色", "白色", ...],
            "mappings": {"原始款号": "目标款号", ...},
        }
    """
    from app.services.erp_sync import ensure_tables
    ensure_tables(db)

    all_sizes: list[str] = []
    all_colors: list[str] = []
    seen_sizes: set[str] = set()
    seen_colors: set[str] = set()

    for pno in (product_nos or []):
        resolved_pno = _resolve_product_no_for_context(db, pno)
        product_row = db.execute(
            text("SELECT color, spec FROM erp_products WHERE product_no = :pno LIMIT 1"),
            {"pno": resolved_pno},
        ).mappings().first()
        if not product_row:
            continue
        for c in (product_row["color"] or "").split(","):
            c = c.strip()
            if c and c not in seen_colors:
                seen_colors.add(c)
                all_colors.append(c)
        for s in (product_row["spec"] or "").split(","):
            s = s.strip()
            if s and s not in seen_sizes:
                seen_sizes.add(s)
                all_sizes.append(s)

    # 款号映射：alias_name（图片中原始款号） → product_no（目标款号）
    mappings: dict[str, str] = {}
    try:
        rows = db.execute(
            text("SELECT product_no, alias_name FROM product_name_mappings ORDER BY product_no"),
        ).mappings().all()
        for r in rows:
            alias = (r["alias_name"] or "").strip()
            target = (r["product_no"] or "").strip()
            if alias and target:
                mappings[alias] = target
    except Exception:
        pass

    return {"sizes": all_sizes, "colors": all_colors, "mappings": mappings}


def _normalize_discount(value: Any) -> int:
    try:
        number = float(value)
    except Exception:
        return 100
    if number <= 1:
        return int(number * 100)
    return int(number)


def _normalize_order(parsed: dict[str, Any], customer_name: str = "") -> dict[str, Any]:
    items = []
    for item in parsed.get("items") or []:
        sizes = []
        for size in item.get("sizes") or []:
            name = str(size.get("size") or "").strip()
            qty = int(size.get("qty") or 0)
            if name and qty:
                sizes.append({"size": name, "qty": qty})
        if not sizes:
            continue
        items.append({
            "product_no": str(item.get("product_no") or "").strip(),
            "product_name": str(item.get("product_name") or "").strip(),
            "color": str(item.get("color") or "").strip(),
            "brand": str(item.get("brand") or "").strip(),
            "unit": str(item.get("unit") or "件").strip() or "件",
            "price": float(item.get("price") or 0),
            "discount": _normalize_discount(item.get("discount") or 100),
            "packaging": str(item.get("packaging") or "").strip(),
            "customer_product_no": str(item.get("customer_product_no") or "").strip(),
            "grade": str(item.get("grade") or "").strip(),
            "product_spec": str(item.get("product_spec") or "").strip(),
            "semi_product_no": str(item.get("semi_product_no") or "").strip(),
            "linked_order_ref": str(item.get("linked_order_ref") or "").strip(),
            "remark": str(item.get("remark") or "").strip(),
            "sizes": sizes,
        })

    order_date = str(parsed.get("order_date") or "").strip()
    if len(order_date) == 10:
        order_date = f"{order_date} 00:00:00"
    if not order_date:
        order_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    return {
        "customer_name": str(parsed.get("customer_name") or customer_name or "").strip(),
        "contact_person": str(parsed.get("contact_person") or "").strip(),
        "order_date": order_date,
        "remark": str(parsed.get("remark") or "").strip(),
        "brand": str(parsed.get("brand") or "").strip(),
        "items": items,
        "uncertainties": parsed.get("uncertainties") or [],
    }


def ensure_review_state(db: Session):
    ensure_downstream_support_tables(db)


def resolve_customer_by_room(db: Session, room_id: str, instance_id: Optional[str] = None) -> Optional[dict[str, Any]]:
    if not room_id:
        return None
    params = {"room_id": room_id}
    sql = (
        "SELECT c.id, c.customer_name, c.contact_person, c.phone, c.address, c.erp_customer_id, r.instance_id, r.room_id, r.room_name "
        "FROM downstream_customer_wechat_rooms r "
        "INNER JOIN downstream_customers c ON c.id = r.customer_id "
        "WHERE r.room_id = :room_id AND c.deleted_at IS NULL AND c.status = 1"
    )
    if instance_id:
        sql += " AND (r.instance_id = :instance_id OR r.instance_id IS NULL)"
        params["instance_id"] = int(instance_id)
    sql += " ORDER BY c.id ASC LIMIT 1"
    return db.execute(text(sql), params).mappings().first()


def serialize_review(row: dict[str, Any]) -> dict[str, Any]:
    item = dict(row)
    item["callback_payload"] = _json_loads(item.get("callback_payload"), {})
    item["parsed_order"] = _json_loads(item.get("parsed_order_json"), None)
    item["manual_order"] = _json_loads(item.get("manual_order_json"), None)
    item["replace_source_rows"] = _json_loads(item.get("replace_source_ids"), [])
    item.pop("parsed_order_json", None)
    item.pop("manual_order_json", None)
    item.pop("replace_source_ids", None)
    return item


def _mask_secret(value: str) -> str:
    text_value = str(value or "")
    if len(text_value) <= 8:
        return "*" * len(text_value)
    return f"{text_value[:4]}***{text_value[-4:]}"


def get_review_attachment_debug(db: Session, review_id: int) -> dict[str, Any]:
    ensure_review_state(db)
    row = db.execute(text("SELECT * FROM downstream_order_reviews WHERE id = :id"), {"id": review_id}).mappings().first()
    if not row:
        raise ValueError("待审核记录不存在")

    payload = _json_loads(row.get("callback_payload"), {})
    runtime = _resolve_wechat_runtime_config(db, row, payload)
    download_request = _extract_download_request_data(payload, row)

    masked_download_request = dict(download_request)
    for sensitive_key in ["auth_key", "aes_key", "file_id"]:
        if sensitive_key in masked_download_request and masked_download_request[sensitive_key]:
            masked_download_request[sensitive_key] = _mask_secret(masked_download_request[sensitive_key])

    return {
        "review_id": review_id,
        "source_type": row.get("source_type") or "",
        "message_type": row.get("message_type") or "",
        "parse_status": row.get("parse_status") or "",
        "review_status": row.get("review_status") or "",
        "attachment_name": row.get("attachment_name") or "",
        "attachment_url": row.get("attachment_url") or "",
        "attachment_mime": row.get("attachment_mime") or "",
        "has_attachment_base64": bool(row.get("attachment_base64")),
        "attachment_base64_length": len(str(row.get("attachment_base64") or "")),
        "ai_error": row.get("ai_error") or "",
        "runtime": {
            "api_base_url": runtime.get("api_base_url") or "",
            "wxid": runtime.get("wxid") or "",
            "api_key_configured": bool(runtime.get("api_key")),
        },
        "download": {
            "ready": bool(runtime.get("api_base_url") and runtime.get("wxid") and download_request),
            "mode": download_request.get("mode") or "",
            "request": masked_download_request,
        },
        "callback_payload": payload,
    }


async def retry_review_attachment_download(db: Session, review_id: int, *, reparse: bool = True, force_download: bool = False) -> dict[str, Any]:
    ensure_review_state(db)
    row = db.execute(text("SELECT * FROM downstream_order_reviews WHERE id = :id"), {"id": review_id}).mappings().first()
    if not row:
        raise ValueError("待审核记录不存在")

    message_type = str(row.get("message_type") or "").lower()
    if message_type not in {"image", "file"}:
        raise ValueError("当前记录不是需要下载附件的图片或文件消息")

    download_result = None
    if force_download or not row.get("attachment_base64"):
        download_result = await _download_review_attachment_content(db, row)
    else:
        download_result = {
            "skipped": True,
            "reason": "attachment_already_exists",
            "attachment_name": row.get("attachment_name") or "",
            "attachment_mime": row.get("attachment_mime") or "",
        }

    parsed_order = None
    parse_error = ""
    if reparse:
        try:
            parsed_order = await parse_review_content(db, review_id)
        except Exception as exc:
            parse_error = str(exc)

    latest = db.execute(text("SELECT * FROM downstream_order_reviews WHERE id = :id"), {"id": review_id}).mappings().first()
    response = {
        "download": download_result,
        "review": serialize_review(latest),
    }
    if parsed_order:
        response["parsed_order"] = parsed_order
    if parse_error:
        response["parse_error"] = parse_error
    return response


async def parse_review_content(db: Session, review_id: int) -> dict[str, Any]:
    ensure_review_state(db)
    row = db.execute(text("SELECT * FROM downstream_order_reviews WHERE id = :id"), {"id": review_id}).mappings().first()
    if not row:
        raise ValueError("待审核记录不存在")

    if str(row.get("message_type") or "").lower() in {"image", "file"} and not row.get("attachment_base64"):
        await _download_review_attachment_content(db, row)
        row = db.execute(text("SELECT * FROM downstream_order_reviews WHERE id = :id"), {"id": review_id}).mappings().first()

    attachment_name = str(row.get("attachment_name") or "").lower()
    attachment_mime = str(row.get("attachment_mime") or "").lower()
    message_type = str(row.get("message_type") or "text").lower()
    customer_hint = str(row.get("customer_name") or row.get("room_name") or "")

    try:
        if message_type in {"image", "file"} and not row.get("attachment_base64"):
            raise AttachmentContentRequiredError("当前消息仅收到附件元数据，请先下载企业微信附件内容后再解析")

        # 构建统一消息列表供 AI 使用
        is_excel = ("excel" in attachment_mime or attachment_name.endswith(".xlsx") or attachment_name.endswith(".xls")) and row.get("attachment_base64")
        is_image = (message_type in {"image", "img", "picture"} or attachment_mime.startswith("image/")) and row.get("attachment_base64")

        context_messages: list[dict[str, Any]] = []
        excel_summary = ""
        if is_excel:
            excel_summary = _extract_excel_summary(row.get("attachment_base64") or "")
            context_messages.append({
                "type": "file",
                "file_name": row.get("attachment_name") or "",
                "excel_summary": excel_summary,
                "content": excel_summary,
            })
        elif is_image:
            context_messages.append({
                "type": "image",
                "base64": row.get("attachment_base64") or "",
                "mime": row.get("attachment_mime") or "image/png",
            })
            if row.get("content_text"):
                context_messages.insert(0, {"type": "text", "content": row.get("content_text")})
        else:
            text_content = row.get("content_text") or row.get("attachment_name") or row.get("room_name") or ""
            context_messages.append({"type": "text", "content": text_content})

        # === 步骤 1：智能体 A — 提取款号 + 判断旋转角度 ===
        logger.info("[AI Parse] review=%d 步骤1: 提取款号...", review_id)
        extract_result = await ai_order_parser.extract_product_nos(context_messages, db=db)
        product_nos = extract_result.get("product_nos") or []
        rotation_angle = extract_result.get("rotation_angle") or 0
        logger.info("[AI Parse] review=%d 提取到款号: %s rotation=%d°", review_id, product_nos, rotation_angle)

        # === 步骤 1.5：根据 AI 判断的角度旋转图片 ===
        if rotation_angle and rotation_angle != 0:
            from app.services.ai_order_parser import rotate_images_in_messages
            context_messages = rotate_images_in_messages(context_messages, rotation_angle)
            logger.info("[AI Parse] review=%d 图片已旋转 %d°", review_id, rotation_angle)

        # === 步骤 2：查询产品表可选颜色/尺码/映射 ===
        context_data = await run_in_threadpool(query_product_context_structured, db, product_nos) if product_nos else {}
        logger.info("[AI Parse] review=%d 步骤2: sizes=%s colors=%d mappings=%d",
                     review_id, context_data.get("sizes"), len(context_data.get("colors", [])),
                     len(context_data.get("mappings", {})))

        # === 步骤 3：智能体 B — 带上下文解析完整订单 ===
        logger.info("[AI Parse] review=%d 步骤3: 带上下文解析订单...", review_id)
        if context_data and (context_data.get("sizes") or context_data.get("colors")):
            parsed = await ai_order_parser.parse_with_product_context(
                context_messages, context_data, customer_hint=customer_hint, db=db,
            )
        else:
            # 没有提取到款号时，回退到原始解析
            if is_excel:
                parsed = await ai_order_parser.parse_excel_summary(row.get("attachment_name") or "", excel_summary, customer_hint)
            elif is_image:
                parsed = await ai_order_parser.parse_image_base64(row.get("attachment_base64") or "", row.get("attachment_mime") or "image/png", row.get("content_text") or "")
            else:
                text_content = row.get("content_text") or row.get("attachment_name") or row.get("room_name") or ""
                parsed = await ai_order_parser.parse_text(text_content, customer_hint)

        normalized = _normalize_order(parsed, customer_hint)
        db.execute(
            text("UPDATE downstream_order_reviews SET parse_status = 'success', ai_error = '', parsed_order_json = :parsed_order_json, updated_at = NOW() WHERE id = :id"),
            {"id": review_id, "parsed_order_json": _json_dumps(normalized)},
        )
        db.commit()
        logger.info("[AI Parse] review=%d 解析完成, items=%d", review_id, len(normalized.get("items") or []))
        return normalized
    except AttachmentContentRequiredError as exc:
        db.execute(
            text("UPDATE downstream_order_reviews SET parse_status = 'pending_attachment', ai_error = :ai_error, updated_at = NOW() WHERE id = :id"),
            {"id": review_id, "ai_error": str(exc)},
        )
        db.commit()
        raise
    except AIOrderParserError as exc:
        db.execute(
            text("UPDATE downstream_order_reviews SET parse_status = 'failed', ai_error = :ai_error, updated_at = NOW() WHERE id = :id"),
            {"id": review_id, "ai_error": str(exc)},
        )
        db.commit()
        raise


async def create_review_from_callback(db: Session, payload: dict[str, Any], instance_id: Optional[str] = None) -> dict[str, Any]:
    ensure_review_state(db)
    message = _extract_callback_message(payload, instance_id)
    if not message.get("is_order_candidate"):
        return {
            "skipped": True,
            "reason": message.get("skip_reason") or "not_order_candidate",
            "message_type": message.get("message_type") or "",
            "room_id": message.get("room_id") or "",
            "source_format": message.get("source_format") or "",
        }

    customer = resolve_customer_by_room(db, message["room_id"], message["instance_id"])
    initial_parse_status = "pending_attachment" if message.get("requires_attachment_download") else "pending"
    result = db.execute(
        text(
            "INSERT INTO downstream_order_reviews ("
            "source_type, instance_id, room_id, room_name, sender_id, sender_name, message_type, content_text, attachment_name, attachment_url, attachment_mime, attachment_base64, callback_payload, parse_status, review_status, customer_id, customer_name"
            ") VALUES ("
            ":source_type, :instance_id, :room_id, :room_name, :sender_id, :sender_name, :message_type, :content_text, :attachment_name, :attachment_url, :attachment_mime, :attachment_base64, :callback_payload, :parse_status, 'pending', :customer_id, :customer_name"
            ")"
        ),
        {
            "source_type": message.get("source_type") or "wechat_generic",
            "instance_id": message.get("instance_id"),
            "room_id": message.get("room_id") or "",
            "room_name": message.get("room_name") or "",
            "sender_id": message.get("sender_id") or "",
            "sender_name": message.get("sender_name") or "",
            "message_type": message.get("message_type") or "text",
            "content_text": message.get("content_text") or "",
            "attachment_name": message.get("attachment_name") or "",
            "attachment_url": message.get("attachment_url") or "",
            "attachment_mime": message.get("attachment_mime") or "",
            "attachment_base64": message.get("attachment_base64") or "",
            "callback_payload": _json_dumps(payload),
            "parse_status": initial_parse_status,
            "customer_id": customer["id"] if customer else None,
            "customer_name": customer["customer_name"] if customer else "",
        },
    )
    review_id = result.lastrowid
    db.commit()

    parsed_order = None
    parse_error = ""
    try:
        parsed_order = await parse_review_content(db, review_id)
    except Exception as exc:
        parse_error = str(exc)

    latest = db.execute(text("SELECT * FROM downstream_order_reviews WHERE id = :id"), {"id": review_id}).mappings().first()
    response = serialize_review(latest)
    if parse_error:
        response["parse_error"] = parse_error
    if parsed_order:
        response["parsed_order"] = parsed_order
    return response


def list_reviews(db: Session, page: int = 1, page_size: int = 20, review_status: str = "", customer_id: Optional[int] = None) -> dict[str, Any]:
    ensure_review_state(db)
    params = {"limit": page_size, "offset": (page - 1) * page_size}
    where_parts = ["1 = 1"]
    if review_status:
        where_parts.append("review_status = :review_status")
        params["review_status"] = review_status
    if customer_id:
        where_parts.append("customer_id = :customer_id")
        params["customer_id"] = customer_id
    where_sql = " AND ".join(where_parts)
    rows = db.execute(
        text(f"SELECT * FROM downstream_order_reviews WHERE {where_sql} ORDER BY created_at DESC LIMIT :limit OFFSET :offset"),
        params,
    ).mappings().all()
    count_params = {key: value for key, value in params.items() if key not in {"limit", "offset"}}
    total = db.execute(text(f"SELECT COUNT(*) AS total FROM downstream_order_reviews WHERE {where_sql}"), count_params).mappings().first()["total"]
    return {
        "list": [serialize_review(row) for row in rows],
        "total": total,
        "page": page,
        "pageSize": page_size,
    }


def get_review_detail(db: Session, review_id: int) -> dict[str, Any]:
    ensure_review_state(db)
    row = db.execute(text("SELECT * FROM downstream_order_reviews WHERE id = :id"), {"id": review_id}).mappings().first()
    if not row:
        raise ValueError("待审核记录不存在")
    return serialize_review(row)


def _load_customer(db: Session, customer_id: int) -> dict[str, Any]:
    customer = db.execute(
        text("SELECT id, customer_name, contact_person, phone, address, erp_customer_id FROM downstream_customers WHERE id = :id AND deleted_at IS NULL AND status = 1"),
        {"id": customer_id},
    ).mappings().first()
    if not customer:
        raise ValueError("客户不存在或已停用")
    return dict(customer)


def _review_order_data(row: dict[str, Any]) -> dict[str, Any]:
    manual_order = _json_loads(row.get("manual_order_json"), None)
    if manual_order:
        return manual_order
    parsed_order = _json_loads(row.get("parsed_order_json"), None)
    if parsed_order:
        return parsed_order
    raise ValueError("当前记录尚无可下单的解析结果")


async def approve_review(db: Session, review_id: int, customer_id: int, current_user: User, review_note: str = "") -> dict[str, Any]:
    row = db.execute(text("SELECT * FROM downstream_order_reviews WHERE id = :id"), {"id": review_id}).mappings().first()
    if not row:
        raise ValueError("待审核记录不存在")
    customer = _load_customer(db, customer_id)
    order_data = _review_order_data(row)
    result = await erp_bridge.create_sales_order(order_data, customer)
    db.execute(
        text(
            "UPDATE downstream_order_reviews SET customer_id = :customer_id, customer_name = :customer_name, review_status = 'approved', erp_order_no = :erp_order_no, review_note = :review_note, reviewer_id = :reviewer_id, reviewer_name = :reviewer_name, reviewed_at = NOW(), updated_at = NOW() WHERE id = :id"
        ),
        {
            "id": review_id,
            "customer_id": customer_id,
            "customer_name": customer.get("customer_name") or "",
            "erp_order_no": result.get("order_no") or "",
            "review_note": review_note,
            "reviewer_id": current_user.id,
            "reviewer_name": current_user.real_name,
        },
    )
    db.commit()
    return {**result, "review_status": "approved"}


async def replace_old_order(db: Session, review_id: int, customer_id: int, current_user: User, review_note: str = "") -> dict[str, Any]:
    row = db.execute(text("SELECT * FROM downstream_order_reviews WHERE id = :id"), {"id": review_id}).mappings().first()
    if not row:
        raise ValueError("待审核记录不存在")
    customer = _load_customer(db, customer_id)
    order_data = _review_order_data(row)
    product_nos = [item.get("product_no") for item in order_data.get("items", []) if item.get("product_no")]
    begin_date = (datetime.now() - timedelta(days=365)).strftime("%Y-%m-%d")
    end_date = datetime.now().strftime("%Y-%m-%d")
    unshipped_rows = await erp_bridge.query_unshipped(customer.get("erp_customer_id") or "", product_nos=product_nos, dates=begin_date, datee=end_date)
    cancel_result = await erp_bridge.cancel_unshipped([item["id"] for item in unshipped_rows])
    create_result = await erp_bridge.create_sales_order(order_data, customer)
    replaced_orders = sorted({item.get("order_no") for item in unshipped_rows if item.get("order_no")})
    db.execute(
        text(
            "UPDATE downstream_order_reviews SET customer_id = :customer_id, customer_name = :customer_name, review_status = 'replaced', erp_order_no = :erp_order_no, replaced_order_no = :replaced_order_no, replace_source_ids = :replace_source_ids, review_note = :review_note, reviewer_id = :reviewer_id, reviewer_name = :reviewer_name, reviewed_at = NOW(), updated_at = NOW() WHERE id = :id"
        ),
        {
            "id": review_id,
            "customer_id": customer_id,
            "customer_name": customer.get("customer_name") or "",
            "erp_order_no": create_result.get("order_no") or "",
            "replaced_order_no": ",".join(replaced_orders),
            "replace_source_ids": _json_dumps(unshipped_rows),
            "review_note": review_note,
            "reviewer_id": current_user.id,
            "reviewer_name": current_user.real_name,
        },
    )
    db.commit()
    return {**create_result, **cancel_result, "review_status": "replaced", "replaced_orders": replaced_orders}


async def manual_order(db: Session, review_id: int, customer_id: int, order_data: dict[str, Any], current_user: User, review_note: str = "") -> dict[str, Any]:
    row = db.execute(text("SELECT id FROM downstream_order_reviews WHERE id = :id"), {"id": review_id}).mappings().first()
    if not row:
        raise ValueError("待审核记录不存在")
    customer = _load_customer(db, customer_id)
    normalized = _normalize_order(order_data, customer.get("customer_name") or "")
    result = await erp_bridge.create_sales_order(normalized, customer)
    db.execute(
        text(
            "UPDATE downstream_order_reviews SET customer_id = :customer_id, customer_name = :customer_name, review_status = 'manual_ordered', manual_order_json = :manual_order_json, erp_order_no = :erp_order_no, review_note = :review_note, reviewer_id = :reviewer_id, reviewer_name = :reviewer_name, reviewed_at = NOW(), updated_at = NOW() WHERE id = :id"
        ),
        {
            "id": review_id,
            "customer_id": customer_id,
            "customer_name": customer.get("customer_name") or "",
            "manual_order_json": _json_dumps(normalized),
            "erp_order_no": result.get("order_no") or "",
            "review_note": review_note,
            "reviewer_id": current_user.id,
            "reviewer_name": current_user.real_name,
        },
    )
    db.commit()
    return {**result, "review_status": "manual_ordered"}


def void_review(db: Session, review_id: int, current_user: User, review_note: str = "") -> dict[str, Any]:
    row = db.execute(text("SELECT id FROM downstream_order_reviews WHERE id = :id"), {"id": review_id}).mappings().first()
    if not row:
        raise ValueError("待审核记录不存在")
    db.execute(
        text(
            "UPDATE downstream_order_reviews SET review_status = 'voided', review_note = :review_note, reviewer_id = :reviewer_id, reviewer_name = :reviewer_name, reviewed_at = NOW(), updated_at = NOW() WHERE id = :id"
        ),
        {
            "id": review_id,
            "review_note": review_note,
            "reviewer_id": current_user.id,
            "reviewer_name": current_user.real_name,
        },
    )
    db.commit()
    return {"review_status": "voided"}
