"""
群聊自动接单处理器
触发方式一: @机器人消息 → AI 预判是否含报货信息 → 含则解析
触发方式二: 图片/文件消息（客户群内） → CDN 下载 → AI 预判 → 含则解析
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

import httpx
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database import SessionLocal, run_in_threadpool

from app.services.ai_order_parser import AIOrderParserError, ai_order_parser
from app.services.downstream_orders import (
    _generate_review_uid,
    _normalize_order,
    ensure_review_state,
    resolve_customer_by_room,
)
from app.services.downstream_support import ensure_downstream_support_tables
from app.services.wechat_reply import send_room_at

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 配置常量
# ---------------------------------------------------------------------------
AT_ORDER_DEDUP_WINDOW = 30        # 同一 room+sender 防重复触发窗口（秒）
MEDIA_DEDUP_WINDOW = 15           # 同一条媒体消息防重复窗口（秒）


# 正在采集中的 (room_id, sender_id) → 启动时间，防重复触发
_active_sessions: dict[tuple[str, str], float] = {}


def _mark_msg_recognized(msg_log_id: int) -> None:
    """标记消息日志已被 AI 识别"""
    if not msg_log_id:
        return
    db = SessionLocal()
    try:
        from app.services.message_logs import mark_ai_recognized
        mark_ai_recognized(db, msg_log_id)
    except Exception as exc:
        logger.warning("标记 ai_recognized 失败 id=%d: %s", msg_log_id, exc)
    finally:
        db.close()

# ---------------------------------------------------------------------------
# 建表
# ---------------------------------------------------------------------------
_DDL_AT_ORDER_CONTEXTS = """
CREATE TABLE IF NOT EXISTS at_order_contexts (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    room_id VARCHAR(100) NOT NULL,
    sender_id VARCHAR(100) NOT NULL,
    customer_id INT UNSIGNED NULL,
    customer_name VARCHAR(255) DEFAULT '',
    instance_id VARCHAR(100) DEFAULT '',
    trigger_message_id BIGINT UNSIGNED NULL,
    context_message_ids TEXT NULL,
    context_summary TEXT NULL,
    review_id BIGINT UNSIGNED NULL,
    status VARCHAR(50) DEFAULT 'pending',
    error_message TEXT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_room_id (room_id),
    INDEX idx_status (status),
    INDEX idx_created_at (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
"""


def ensure_at_order_tables(db: Session) -> None:
    db.execute(text(_DDL_AT_ORDER_CONTEXTS))
    db.commit()


# ---------------------------------------------------------------------------
# @检测
# ---------------------------------------------------------------------------
def is_at_bot(payload: dict[str, Any], bot_wxid: str, instance_id: str = "") -> bool:
    """检测消息是否 @了机器人（同时匹配 wxid 和 instance_id）"""
    # 构建所有可能匹配的 bot 标识
    bot_ids: set[str] = set()
    if bot_wxid:
        bot_ids.add(bot_wxid)
    if instance_id:
        bot_ids.add(str(instance_id))
    if not bot_ids:
        return False

    message = payload.get("message") if isinstance(payload.get("message"), dict) else {}
    message_data = message.get("data") if isinstance(message.get("data"), dict) else {}
    if not message_data and isinstance(payload.get("data"), dict):
        message_data = payload["data"]

    # 方式 1: at_list 包含 bot wxid 或 instance_id
    at_list = message_data.get("at_list") or payload.get("at_list") or []
    if isinstance(at_list, str):
        try:
            at_list = json.loads(at_list)
        except Exception:
            at_list = [at_list]
    if isinstance(at_list, list):
        for item in at_list:
            if isinstance(item, dict):
                uid = str(item.get("user_id", "")).strip()
                if uid and uid in bot_ids:
                    return True
            elif isinstance(item, str) and item.strip() in bot_ids:
                return True

    # 方式 2: is_at_me 标识
    if message_data.get("is_at_me") is True or payload.get("is_at_me") is True:
        return True

    return False


def extract_trigger_info(payload: dict[str, Any], instance_id: Optional[str] = None) -> dict[str, Any]:
    """从 payload 中提取触发消息的关键信息"""
    message = payload.get("message") if isinstance(payload.get("message"), dict) else {}
    message_data = message.get("data") if isinstance(message.get("data"), dict) else {}
    if not message_data and isinstance(payload.get("data"), dict):
        message_data = payload["data"]

    sender_id = (
        message_data.get("sender")
        or message_data.get("from_wxid")
        or payload.get("sender_id")
        or payload.get("sender")
        or ""
    )
    room_id = (
        message_data.get("conversation_id")
        or message_data.get("room_wxid")
        or payload.get("room_id")
        or payload.get("conversation_id")
        or ""
    )
    # 去掉 R: 前缀以统一格式
    if isinstance(room_id, str) and room_id.startswith("R:"):
        room_id = room_id[2:]

    content = (
        message_data.get("content")
        or message_data.get("text_content")
        or message_data.get("msg")
        or payload.get("content")
        or ""
    )
    resolved_instance = (
        instance_id
        or payload.get("instanceId")
        or payload.get("instance_id")
        or payload.get("wxid")
        or ""
    )
    return {
        "sender_id": str(sender_id).strip(),
        "room_id": str(room_id).strip(),
        "content": str(content).strip(),
        "instance_id": str(resolved_instance).strip(),
    }


# ---------------------------------------------------------------------------
# 媒体消息防重复：记录已处理的 message_log id
# ---------------------------------------------------------------------------
_processed_media: dict[int, float] = {}   # msg_log_id → monotonic timestamp


# ---------------------------------------------------------------------------
# 消息转换为 AI 输入
# ---------------------------------------------------------------------------
def _safe_json_loads(data: Any, default: Any = None):
    if not data:
        return default
    if isinstance(data, (dict, list)):
        return data
    try:
        return json.loads(data)
    except Exception:
        return default


def _msg_to_ai_input(msg: dict[str, Any]) -> dict[str, Any]:
    """将 message_logs 行转换为 parse_batch 所需的输入格式"""
    msg_type = str(msg.get("message_type") or "text").lower()
    content = str(msg.get("content_preview") or "")
    payload = _safe_json_loads(msg.get("payload_json"), {})
    sender_name = str(msg.get("sender_name") or "").strip()

    if msg_type in ("text",):
        return {"type": "text", "content": content, "sender_name": sender_name}

    if msg_type in ("image", "img", "picture"):
        # 图片 base64 需要从 payload 提取或后续下载
        message_data = {}
        if isinstance(payload, dict):
            message = payload.get("message") if isinstance(payload.get("message"), dict) else {}
            message_data = message.get("data") if isinstance(message.get("data"), dict) else {}

        # 尝试从 payload 中直接获取 base64
        img_b64 = (
            payload.get("file_base64")
            or payload.get("base64")
            or message_data.get("file_base64")
            or ""
        )
        mime = "image/png"
        return {"type": "image", "base64": img_b64, "mime": mime, "content": content, "sender_name": sender_name, "_payload": payload, "_msg_id": msg.get("id")}

    if msg_type in ("file",):
        file_name = ""
        if isinstance(payload, dict):
            message = payload.get("message") if isinstance(payload.get("message"), dict) else {}
            message_data = message.get("data") if isinstance(message.get("data"), dict) else {}
            file_name = (
                message_data.get("file_name")
                or payload.get("file_name")
                or payload.get("filename")
                or ""
            )
        return {"type": "file", "file_name": file_name, "content": content, "sender_name": sender_name, "_payload": payload, "_msg_id": msg.get("id")}

    return {"type": "text", "content": content, "sender_name": sender_name}


def _resolve_wechat_runtime_for_download(db: Session, instance_id: str) -> dict[str, Any]:
    """解析企微运行时配置供 CDN 下载使用"""
    if instance_id:
        from app.models import WechatInstance
        inst = db.query(WechatInstance).filter(
            (WechatInstance.wxid == instance_id) | (WechatInstance.id == instance_id)
        ).first()
        if inst:
            return {
                "api_base_url": (inst.api_base_url or "").rstrip("/"),
                "api_key": inst.api_key or "",
                "wxid": inst.wxid or "",
            }
    try:
        row = db.execute(text("SELECT host, port, api_key, selected_wxid FROM wechat_config WHERE id = 1")).mappings().first()
    except Exception:
        row = None
    if row:
        host = (row.get("host") or "").strip()
        port = (row.get("port") or "").strip()
        base = ""
        if host:
            base = host if host.startswith(("http://", "https://")) else f"http://{host}"
            if port and port not in ("80", "443"):
                base = f"{base}:{port}"
        return {
            "api_base_url": base.rstrip("/"),
            "api_key": row.get("api_key") or "",
            "wxid": row.get("selected_wxid") or instance_id,
        }
    return {"api_base_url": "", "api_key": "", "wxid": instance_id}


def _extract_cdn_params(payload: dict[str, Any]) -> dict[str, Any]:
    """从 payload 中提取 CDN 下载参数"""
    message = payload.get("message") if isinstance(payload.get("message"), dict) else {}
    data = message.get("data") if isinstance(message.get("data"), dict) else {}
    cdn = data.get("cdn") if isinstance(data.get("cdn"), dict) else {}
    c2c = data.get("c2c_cdn") if isinstance(data.get("c2c_cdn"), dict) else {}

    # wx_download
    url = cdn.get("url") or data.get("url") or ""
    auth_key = cdn.get("auth_key") or data.get("auth_key") or ""
    aes_key = cdn.get("aes_key") or c2c.get("aes_key") or data.get("aes_key") or ""
    size = cdn.get("size") or c2c.get("file_size") or c2c.get("size") or data.get("size") or 0
    try:
        size = int(size)
    except (ValueError, TypeError):
        size = 0

    if url and auth_key and aes_key and size:
        return {"mode": "wx_download", "url": url, "auth_key": auth_key, "aes_key": aes_key, "size": size}

    file_id = c2c.get("file_id") or data.get("file_id") or ""
    if file_id and aes_key:
        return {"mode": "c2c_download", "file_id": file_id, "aes_key": aes_key, "file_size": size, "file_type": 5}

    return {}


async def _download_attachment_for_msg(db: Session, ai_input: dict[str, Any], room_id: str, instance_id: str) -> None:
    """为图片/文件消息下载附件并填充 base64"""
    payload = ai_input.get("_payload") or {}
    if not payload:
        return

    msg_type = ai_input.get("type", "")
    if msg_type == "image" and ai_input.get("base64"):
        return

    cdn_params = _extract_cdn_params(payload)
    if not cdn_params:
        logger.debug("附件下载: 无 CDN 参数 msg_id=%s", ai_input.get("_msg_id"))
        return

    runtime = _resolve_wechat_runtime_for_download(db, instance_id)
    if not runtime.get("api_base_url") or not runtime.get("wxid"):
        logger.warning("附件下载: 缺少运行时配置")
        return

    ext = ".png" if msg_type == "image" else ".dat"
    fname = ai_input.get("file_name") or ""
    if fname:
        ext = Path(fname).suffix or ext
    download_dir = Path(__file__).resolve().parents[2] / "temp" / "at_order_attachments"
    download_dir.mkdir(parents=True, exist_ok=True)
    save_path = download_dir / f"msg_{ai_input.get('_msg_id', 0)}{ext}"

    mode = cdn_params.pop("mode")
    api_route = f"cdn/{mode}"
    cdn_params["save_path"] = str(save_path)

    headers: dict[str, str] = {}
    if runtime.get("api_key"):
        headers["X-API-Key"] = runtime["api_key"]

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                f"{runtime['api_base_url']}/api/{runtime['wxid']}/{api_route}",
                json=cdn_params,
                headers=headers,
            )
            resp.raise_for_status()

        # 解析响应，检查 bot API 返回的实际保存路径
        response_payload: dict[str, Any] = {}
        try:
            response_payload = resp.json()
            resp_data = response_payload.get("data") if isinstance(response_payload.get("data"), dict) else {}
            if response_payload.get("code") not in (0, None):
                logger.warning("附件下载: API 返回错误 code=%s msg=%s",
                               response_payload.get("code"), response_payload.get("msg"))
                return
        except Exception:
            pass

        if not save_path.is_file():
            # bot API 可能将文件保存到了不同的路径，从响应中查找真实路径
            resp_data = response_payload.get("data") if isinstance(response_payload.get("data"), dict) else {}
            for key in ("save_path", "path", "file_path"):
                possible = str(resp_data.get(key) or "").strip()
                if possible and Path(possible).is_file():
                    save_path = Path(possible)
                    logger.info("附件下载: 使用响应中的路径 %s", save_path)
                    break
        if not save_path.is_file():
            logger.warning("附件下载: 文件未出现 requested=%s response=%s",
                           cdn_params.get("save_path"), response_payload)
            return

        file_bytes = save_path.read_bytes()
        b64 = base64.b64encode(file_bytes).decode("ascii")
        ai_input["base64"] = b64
        if msg_type == "image":
            ai_input["mime"] = "image/png"

        if fname.lower().endswith((".xlsx", ".xls")):
            try:
                from app.services.downstream_orders import _extract_excel_summary
                ai_input["excel_summary"] = _extract_excel_summary(b64)
            except Exception:
                pass
    except Exception as exc:
        logger.warning("附件下载失败 msg_id=%s: %s", ai_input.get("_msg_id"), exc)


# ---------------------------------------------------------------------------
# 库存校验 & 二次解析
# ---------------------------------------------------------------------------
def _build_name_mapping_hints(db: Session) -> str:
    """构建名称映射提示文本，告诉 AI 哪些别名对应哪个货号"""
    try:
        rows = db.execute(
            text("SELECT product_no, alias_name FROM product_name_mappings ORDER BY product_no, alias_name"),
        ).mappings().all()
    except Exception:
        return ""
    if not rows:
        return ""
    # 按货号分组
    mapping: dict[str, list[str]] = {}
    for r in rows:
        pno = r["product_no"]
        mapping.setdefault(pno, []).append(r["alias_name"])
    lines = ["产品名称映射（客户可能用别名代替货号）："]
    for pno, aliases in mapping.items():
        lines.append(f"  货号 {pno} = {', '.join(aliases)}")
    return "\n".join(lines)


def _resolve_product_no(db: Session, name: str) -> str:
    """通过映射表解析名称 → 货号。

    优先级：映射表 > 产品表精确匹配 > 原值
    映射表优先，确保用户显式配置的别名总是生效。
    """
    name = name.strip()
    if not name:
        return name
    # 1. 优先查映射表——用户显式配置的别名拥有最高优先级
    alias = db.execute(
        text("SELECT product_no FROM product_name_mappings WHERE alias_name = :name LIMIT 1"),
        {"name": name},
    ).mappings().first()
    if alias:
        return alias["product_no"]
    # 2. 直接在产品表匹配货号
    direct = db.execute(
        text("SELECT product_no FROM erp_products WHERE product_no = :name LIMIT 1"),
        {"name": name},
    ).mappings().first()
    if direct:
        return direct["product_no"]
    return name


def _query_product_colors_sizes(db: Session, product_no: str) -> dict[str, Any]:
    """查询指定货号在 erp_inventory 中的所有颜色及对应尺码"""
    rows = db.execute(
        text(
            "SELECT color, sizes_json FROM erp_inventory "
            "WHERE product_no = :pno AND qty > 0"
        ),
        {"pno": product_no},
    ).mappings().all()
    colors: dict[str, list[str]] = {}
    for r in rows:
        color = r["color"] or ""
        sizes_raw = r["sizes_json"] or "[]"
        try:
            sizes = json.loads(sizes_raw)
        except Exception:
            sizes = []
        size_names = [s["size"] for s in sizes if s.get("size")]
        if color in colors:
            for s in size_names:
                if s not in colors[color]:
                    colors[color].append(s)
        else:
            colors[color] = size_names
    return colors


def validate_order_against_inventory(db: Session, parsed_order: dict[str, Any]) -> dict[str, Any]:
    """校验 AI 解析结果中的每个 item 的货号、颜色、尺码是否在库存中。

    返回:
        {
            "all_valid": bool,
            "items_result": [
                {
                    "item": <原item>,
                    "valid": bool,
                    "product_found": bool,
                    "color_found": bool,
                    "sizes_issues": ["XS 不存在"],
                    "available_colors_sizes": {颜色: [尺码]}  # 仅 product_found 时
                }
            ]
        }
    """
    items = parsed_order.get("items") or []
    items_result = []
    all_valid = True

    for item in items:
        product_no = (item.get("product_no") or "").strip()
        color = (item.get("color") or "").strip()
        sizes = item.get("sizes") or []

        result = {
            "item": item,
            "valid": True,
            "product_found": False,
            "color_found": False,
            "sizes_issues": [],
            "available_colors_sizes": {},
        }

        if not product_no:
            result["valid"] = False
            all_valid = False
            items_result.append(result)
            continue

        # 通过名称映射解析真实货号
        resolved_no = _resolve_product_no(db, product_no)
        if resolved_no != product_no:
            logger.info("名称映射: %s -> %s", product_no, resolved_no)
            item["product_no"] = resolved_no
            product_no = resolved_no

        # 查库存
        available = _query_product_colors_sizes(db, product_no)
        result["available_colors_sizes"] = available

        if not available:
            result["valid"] = False
            result["product_found"] = False
            all_valid = False
            items_result.append(result)
            continue

        result["product_found"] = True

        # 检查颜色
        if color and color in available:
            result["color_found"] = True
        elif color:
            result["color_found"] = False
            result["valid"] = False
            all_valid = False
        else:
            result["color_found"] = False
            result["valid"] = False
            all_valid = False

        # 检查尺码
        if result["color_found"] and available.get(color):
            available_sizes = available[color]
            for s in sizes:
                size_name = s.get("size", "")
                if size_name and size_name not in available_sizes:
                    result["sizes_issues"].append(f"{size_name} 不存在")
                    result["valid"] = False
                    all_valid = False

        items_result.append(result)

    return {"all_valid": all_valid, "items_result": items_result}


def _build_product_hints_text(validation_result: dict[str, Any]) -> str:
    """从校验结果中构建产品可选颜色/尺码的提示文本，用于 AI 二次解析"""
    lines = []
    seen_products = set()
    for ir in validation_result.get("items_result", []):
        pno = (ir["item"].get("product_no") or "").strip()
        if not pno or pno in seen_products:
            continue
        seen_products.add(pno)
        available = ir.get("available_colors_sizes") or {}
        if not available:
            lines.append(f"款号 {pno}：库存中未找到该货号")
            continue
        color_parts = []
        for color, sizes in available.items():
            color_parts.append(f"  {color}: {', '.join(sizes)}")
        lines.append(f"款号 {pno} 可选颜色和尺码：")
        lines.extend(color_parts)
    return "\n".join(lines)


REPARSE_SYSTEM_PROMPT = """你是一个服装订单解析助手。客户发来的订单已经过一次解析，但部分颜色或尺码与库存不匹配。
现在提供该货号的所有可选颜色和尺码，请你重新匹配：
- 客户说的"白色"可能对应"米白"、"乳白"、"象牙白"等，请根据可选颜色智能匹配
- 客户说的尺码缩写（如"大"、"中"、"小"）请匹配为标准尺码（S/M/L/XL/2XL/3XL等）
- 如果确实无法匹配，保留原值并在 uncertainties 中说明
- 严格返回 JSON，不要返回 markdown
返回结构与原始订单相同：
{
  "customer_name": "",
  "contact_person": "",
  "order_date": "YYYY-MM-DD",
  "remark": "",
  "items": [
    {
      "product_no": "",
      "product_name": "",
      "color": "",
      "brand": "",
      "unit": "件",
      "price": 0,
      "discount": 1,
      "sizes": [{"size": "S", "qty": 1}],
      "remark": ""
    }
  ],
  "uncertainties": []
}
"""


async def reparse_with_product_hints(
    ai_inputs: list[dict[str, Any]],
    first_parse_result: dict[str, Any],
    validation_result: dict[str, Any],
    customer_hint: str = "",
    db: Optional[Session] = None,
) -> dict[str, Any]:
    """用库存颜色/尺码提示信息让 AI 重新解析订单"""
    product_hints = _build_product_hints_text(validation_result)

    cfg = ai_order_parser._load_config(db)
    ai_order_parser._ensure_enabled(cfg)
    has_image = any(m.get("type") == "image" for m in ai_inputs)
    model = cfg["vision_model"] if has_image else cfg["model"]

    user_parts: list[dict[str, Any]] = []
    user_parts.append({
        "type": "text",
        "text": (
            f"客户提示: {customer_hint or '无'}\n\n"
            f"=== 第一次解析结果 ===\n{json.dumps(first_parse_result, ensure_ascii=False, indent=2)}\n\n"
            f"=== 库存可选颜色和尺码 ===\n{product_hints}\n\n"
            f"请根据以上库存信息重新匹配颜色和尺码，输出修正后的完整订单 JSON。\n"
            f"以下是客户原始消息供参考："
        ),
    })

    for idx, msg in enumerate(ai_inputs, 1):
        msg_type = msg.get("type", "text")
        if msg_type == "text":
            user_parts.append({"type": "text", "text": f"[消息{idx}] {msg.get('content', '')}"})
        elif msg_type == "image":
            if msg.get("oss_url"):
                user_parts.append({"type": "text", "text": f"[消息{idx}] 图片:"})
                user_parts.append({"type": "image_url", "image_url": {"url": msg["oss_url"]}})
            elif msg.get("base64"):
                mime = msg.get("mime") or "image/png"
                user_parts.append({"type": "text", "text": f"[消息{idx}] 图片:"})
                user_parts.append({"type": "image_url", "image_url": {"url": f"data:{mime};base64,{msg['base64']}"}})
        elif msg_type == "file":
            summary = msg.get("excel_summary") or msg.get("content") or ""
            fname = msg.get("file_name") or "附件"
            user_parts.append({"type": "text", "text": f"[消息{idx}] 文件 {fname}:\n{summary}"})

    return await ai_order_parser._chat(
        model,
        [
            {"role": "system", "content": REPARSE_SYSTEM_PROMPT},
            {"role": "user", "content": user_parts},
        ],
        db=db,
        caller="reparse_with_hints",
    )


# ---------------------------------------------------------------------------
# 写入审核队列
# ---------------------------------------------------------------------------
def _build_context_summary(ai_inputs: list[dict[str, Any]]) -> str:
    """生成上下文文本摘要"""
    parts = []
    for inp in ai_inputs:
        if inp.get("type") == "text":
            parts.append(inp.get("content", ""))
        elif inp.get("type") == "image":
            parts.append("[图片]")
        elif inp.get("type") == "file":
            parts.append(f"[文件] {inp.get('file_name', '')}")
    return "\n".join(parts)[:2000]


def _write_review(
    db: Session,
    parsed_order: dict[str, Any],
    customer: dict[str, Any],
    room_id: str,
    sender_id: str,
    instance_id: str,
    context_summary: str,
    parse_status: str = "success",
    ai_error: str = "",
    msg_log_id: int = 0,
    message_type: str = "text",
) -> int:
    """写入 downstream_order_reviews 表"""
    ensure_review_state(db)

    # 从 msg_log_id 补全 room_name / sender_name / message_type
    room_name = ""
    sender_name = ""
    if msg_log_id:
        try:
            log_row = db.execute(
                text("SELECT room_name, sender_name, message_type FROM message_logs WHERE id = :id"),
                {"id": msg_log_id},
            ).mappings().first()
            if log_row:
                room_name = log_row.get("room_name") or ""
                sender_name = log_row.get("sender_name") or ""
                if message_type == "text" and log_row.get("message_type"):
                    message_type = log_row["message_type"]
        except Exception:
            pass

    # 从 wechat_room_listeners 补全 room_name
    if not room_name and room_id:
        try:
            from app.services.wechat_room_cache import get_room_name
            room_name = get_room_name(room_id)
        except Exception:
            pass
        if not room_name:
            try:
                r = db.execute(
                    text("SELECT room_name FROM wechat_room_listeners WHERE room_id = :rid LIMIT 1"),
                    {"rid": room_id},
                ).mappings().first()
                if r:
                    room_name = r.get("room_name") or ""
            except Exception:
                pass

    review_uid = _generate_review_uid()
    result = db.execute(
        text(
            "INSERT INTO downstream_order_reviews ("
            "review_uid, source_type, instance_id, room_id, room_name, sender_id, sender_name, message_type, content_text, "
            "parse_status, review_status, customer_id, customer_name, "
            "parsed_order_json, ai_error, msg_log_id"
            ") VALUES ("
            ":review_uid, 'wechat_at_order', :instance_id, :room_id, :room_name, :sender_id, :sender_name, :message_type, :content_text, "
            ":parse_status, 'pending', :customer_id, :customer_name, "
            ":parsed_order_json, :ai_error, :msg_log_id"
            ")"
        ),
        {
            "review_uid": review_uid,
            "instance_id": instance_id,
            "room_id": room_id,
            "room_name": room_name,
            "sender_id": sender_id,
            "sender_name": sender_name,
            "message_type": message_type,
            "content_text": context_summary,
            "parse_status": parse_status,
            "customer_id": customer.get("id"),
            "customer_name": customer.get("customer_name") or "",
            "parsed_order_json": json.dumps(parsed_order, ensure_ascii=False) if parsed_order else None,
            "ai_error": ai_error,
            "msg_log_id": msg_log_id or None,
        },
    )
    db.commit()
    review_id = result.lastrowid
    from app.services.review_events import notify_review_change
    notify_review_change("new_review", {"review_id": review_id})
    return review_id


# ---------------------------------------------------------------------------
# 共享：解析 + 校验 + 写审核 + 群回复
# ---------------------------------------------------------------------------
async def _process_order(
    ai_inputs: list[dict[str, Any]],
    customer: dict[str, Any],
    room_id: str,
    sender_id: str,
    instance_id: str,
    trigger_msg_id: int,
    source_label: str = "接单",
) -> None:
    """AI 解析 → 库存校验 → 写审核 → 群回复。@接单和媒体接单共用。"""
    context_summary = _build_context_summary(ai_inputs)
    customer_hint = customer.get("customer_name") or ""

    db = SessionLocal()
    try:
        from app.services.erp_sync import ensure_tables
        from app.services.downstream_orders import query_product_context_structured, query_current_year_catalog
        await run_in_threadpool(ensure_tables, db)

        # === 步骤 1：智能体 A — 从本年产品目录匹配款号 + 判断旋转角度 ===
        logger.info("%s: 步骤1 加载本年产品目录并匹配款号 room=%s", source_label, room_id)
        catalog = await run_in_threadpool(query_current_year_catalog, db)
        catalog_pnos_sample = [item["product_no"] for item in catalog[:10]]
        logger.info("%s: 本年产品目录: %d 个产品, 前10个: %s room=%s", source_label, len(catalog), catalog_pnos_sample, room_id)
        extract_result = await ai_order_parser.extract_product_nos(ai_inputs, db=db, catalog=catalog)
        product_nos = extract_result.get("product_nos") or []
        rotation_angle = extract_result.get("rotation_angle") or 0
        logger.info("%s: 步骤1结果 提取到款号: %s rotation=%d° room=%s", source_label, product_nos, rotation_angle, room_id)

        # === 步骤 1.5：根据 AI 判断的角度旋转图片 ===
        if rotation_angle and rotation_angle != 0:
            from app.services.ai_order_parser import rotate_images_in_messages
            ai_inputs = rotate_images_in_messages(ai_inputs, rotation_angle)
            logger.info("%s: 图片已旋转 %d° room=%s", source_label, rotation_angle, room_id)

        # === 步骤 2：查询产品表可选颜色/尺码/映射 ===
        context_data = await run_in_threadpool(query_product_context_structured, db, product_nos) if product_nos else {}
        products_ctx = context_data.get("products") or {}
        logger.info("%s: 步骤2 产品上下文 products=%d个款号 mappings=%d room=%s",
                     source_label, len(products_ctx), len(context_data.get("mappings", {})), room_id)
        for pno, info in products_ctx.items():
            logger.info("%s:   款号 %s: 颜色%s 尺码%s", source_label, pno, info.get("colors"), info.get("sizes"))

        # === 步骤 3：智能体 B — 带上下文解析完整订单 ===
        if context_data and context_data.get("products"):
            logger.info("%s: 步骤3 走 parse_with_product_context(有上下文) room=%s", source_label, room_id)
            parsed = await ai_order_parser.parse_with_product_context(
                ai_inputs, context_data, customer_hint=customer_hint, db=db,
            )
        else:
            logger.info("%s: 步骤3 走 parse_batch(无上下文, 带目录约束) room=%s", source_label, room_id)
            parsed = await ai_order_parser.parse_batch(ai_inputs, customer_hint=customer_hint, db=db, catalog=catalog)

        logger.info("%s: 步骤3 AI原始返回keys=%s room=%s", source_label, list(parsed.keys()) if isinstance(parsed, dict) else type(parsed).__name__, room_id)
        final_order = _normalize_order(parsed, customer_hint)
        logger.info("%s: 步骤3 normalize后 items=%s room=%s", source_label,
                     [{"pno": it.get("product_no"), "color": it.get("color")} for it in (final_order.get("items") or [])], room_id)

        # 软校验：标记不在本年产品目录中的款号（但不过滤，保留所有数据）
        if catalog:
            valid_pnos = {item["product_no"] for item in catalog}
            unknown_pnos = {it.get("product_no") for it in (final_order.get("items") or [])
                           if it.get("product_no") and it["product_no"] not in valid_pnos}
            if unknown_pnos:
                logger.warning("%s: 以下款号不在本年产品目录中(保留不过滤): %s room=%s",
                               source_label, unknown_pnos, room_id)

        logger.info("%s: 解析完成 room=%s items=%d", source_label, room_id, len(final_order.get("items") or []))

        review_id = _write_review(
            db, final_order, customer, room_id, sender_id, instance_id, context_summary,
            parse_status="success", msg_log_id=trigger_msg_id,
        )

        ensure_at_order_tables(db)
        db.execute(
            text(
                "INSERT INTO at_order_contexts ("
                "room_id, sender_id, customer_id, customer_name, instance_id, "
                "trigger_message_id, context_message_ids, context_summary, review_id, status"
                ") VALUES ("
                ":room_id, :sender_id, :customer_id, :customer_name, :instance_id, "
                ":trigger_message_id, :context_message_ids, :context_summary, :review_id, 'success'"
                ")"
            ),
            {
                "room_id": room_id,
                "sender_id": sender_id,
                "customer_id": customer.get("id"),
                "customer_name": customer.get("customer_name") or "",
                "instance_id": instance_id,
                "trigger_message_id": trigger_msg_id,
                "context_message_ids": json.dumps([trigger_msg_id]),
                "context_summary": context_summary[:2000],
                "review_id": review_id,
            },
        )
        db.commit()

        items = final_order.get("items") or []
        total_qty = sum(sum(s.get("qty", 0) for s in it.get("sizes", [])) for it in items)
        product_list = ", ".join(it.get("product_no", "?") for it in items[:5])
        if len(items) > 5:
            product_list += f"...等{len(items)}款"
        reply = f"✅ 订单已识别：{product_list} 共{total_qty}件，已提交审核，请等待确认"
        await send_room_at(db, room_id, reply, at_list=[sender_id])

    except (AIOrderParserError, Exception) as exc:
        logger.error("%s: AI 解析失败 room=%s sender=%s: %s", source_label, room_id, sender_id, exc)
        try:
            _write_review(
                db, {}, customer, room_id, sender_id, instance_id, context_summary,
                parse_status="failed", ai_error=str(exc),
            )
            ensure_at_order_tables(db)
            db.execute(
                text(
                    "INSERT INTO at_order_contexts ("
                    "room_id, sender_id, customer_id, customer_name, instance_id, "
                    "trigger_message_id, context_summary, status, error_message"
                    ") VALUES ("
                    ":room_id, :sender_id, :customer_id, :customer_name, :instance_id, "
                    ":trigger_message_id, :context_summary, 'failed', :error_message"
                    ")"
                ),
                {
                    "room_id": room_id,
                    "sender_id": sender_id,
                    "customer_id": customer.get("id"),
                    "customer_name": customer.get("customer_name") or "",
                    "instance_id": instance_id,
                    "trigger_message_id": trigger_msg_id,
                    "context_summary": context_summary[:2000],
                    "error_message": str(exc)[:2000],
                },
            )
            db.commit()
        except Exception:
            pass
        await send_room_at(db, room_id, "⚠️ 无法识别订单内容，请重新发送或联系客服", at_list=[sender_id])
    finally:
        db.close()


# ---------------------------------------------------------------------------
# 主入口 1：@机器人 触发
# ---------------------------------------------------------------------------
async def handle_at_order(
    room_id: str,
    sender_id: str,
    customer: dict[str, Any],
    trigger_msg_id: int,
    instance_id: str = "",
    trigger_content: str = "",
) -> None:
    """@机器人消息 → AI 预判 → 含报货信息则解析"""
    session_key = (room_id, sender_id)

    now = time.monotonic()
    if session_key in _active_sessions:
        if now - _active_sessions[session_key] < AT_ORDER_DEDUP_WINDOW:
            logger.info("@接单: 防重复跳过 room=%s sender=%s", room_id, sender_id)
            return
    _active_sessions[session_key] = now

    try:
        logger.info("@接单: 收到 @消息 room=%s sender=%s content=%s",
                     room_id, sender_id, (trigger_content or "")[:80])

        if not trigger_content or not trigger_content.strip():
            logger.info("@接单: @消息无文字内容，跳过 room=%s", room_id)
            return

        # 1. 智能体1：验证这条 @消息是否包含报货信息
        ai_input_for_judge = [{"type": "text", "content": trigger_content}]
        db = SessionLocal()
        try:
            validation = await ai_order_parser.validate_order(ai_input_for_judge, db=db)
        finally:
            db.close()

        if not validation.get("is_order"):
            logger.info("@接单: 智能体1判定非报单 room=%s reason=%s", room_id, validation.get("reason"))
            _mark_msg_recognized(trigger_msg_id)
            return

        logger.info("@接单: 智能体1判定为报单 room=%s complete=%s missing=%s reason=%s",
                     room_id, validation.get("is_complete"), validation.get("missing_fields"), validation.get("reason"))

        # 信息不完整时提醒客户补充
        if not validation.get("is_complete"):
            missing = validation.get("missing_fields") or []
            missing_str = "、".join(missing) if missing else "部分信息"
            db = SessionLocal()
            try:
                await send_room_at(db, room_id,
                    f"📋 检测到报货信息，但缺少：{missing_str}，请补充完整后重新发送",
                    at_list=[sender_id])
            finally:
                db.close()
            _mark_msg_recognized(trigger_msg_id)
            return

        # 2. 智能体2：完整解析
        valid_inputs = [{"type": "text", "content": trigger_content}]
        await _process_order(
            valid_inputs, customer, room_id, sender_id, instance_id, trigger_msg_id,
            source_label="@接单",
        )
        _mark_msg_recognized(trigger_msg_id)

    except Exception as exc:
        logger.exception("@接单: 未知错误 room=%s sender=%s: %s", room_id, sender_id, exc)
    finally:
        _active_sessions.pop(session_key, None)


# ---------------------------------------------------------------------------
# 主入口 2：图片/文件消息自动触发
# ---------------------------------------------------------------------------
async def handle_media_order(
    room_id: str,
    sender_id: str,
    customer: dict[str, Any],
    msg_log_id: int,
    instance_id: str = "",
    payload: dict[str, Any] | None = None,
    message_type: str = "image",
) -> None:
    """客户群内收到图片/文件 → CDN 下载 → AI 预判 → 含报货信息则解析"""
    if not payload:
        return

    # 防重复
    now = time.monotonic()
    if msg_log_id in _processed_media:
        if now - _processed_media[msg_log_id] < MEDIA_DEDUP_WINDOW:
            return
    _processed_media[msg_log_id] = now
    # 清理过期记录
    cutoff = now - 300
    for k in [k for k, v in _processed_media.items() if v < cutoff]:
        _processed_media.pop(k, None)

    try:
        logger.info("媒体接单: 收到 %s room=%s sender=%s log_id=%d",
                     message_type, room_id, sender_id, msg_log_id)

        # 1. 构造 ai_input 并下载附件
        ai_input: dict[str, Any] = {
            "type": message_type,
            "_payload": payload,
            "_msg_id": msg_log_id,
        }
        if message_type == "image":
            ai_input["mime"] = "image/png"
        else:
            # 提取文件名，仅处理 Excel 文件
            msg_data = (payload.get("message") or {}).get("data") or payload.get("data") or {}
            if isinstance(msg_data, str):
                msg_data = {}
            fname = str(
                msg_data.get("file_name") or payload.get("file_name") or payload.get("filename") or ""
            )
            if not fname.lower().endswith((".xlsx", ".xls")):
                logger.info("媒体接单: 非 Excel 文件，跳过 room=%s file=%s", room_id, fname)
                return
            ai_input["file_name"] = fname
            ai_input["content"] = fname

        db = SessionLocal()
        try:
            await _download_attachment_for_msg(db, ai_input, room_id, instance_id)
        finally:
            db.close()

        if not ai_input.get("base64") and not ai_input.get("excel_summary"):
            logger.info("媒体接单: 下载失败或无内容 room=%s log_id=%d", room_id, msg_log_id)
            return

        # 清理内部字段
        ai_input.pop("_payload", None)
        ai_input.pop("_msg_id", None)

        # 2. 智能体1：验证是否为报货信息（直接用 base64，不存图片）
        ai_input_for_judge = [ai_input]
        db = SessionLocal()
        try:
            validation = await ai_order_parser.validate_order(ai_input_for_judge, db=db)
        finally:
            db.close()

        if not validation.get("is_order"):
            logger.info("媒体接单: 智能体1判定非报单 room=%s log_id=%d reason=%s",
                         room_id, msg_log_id, validation.get("reason"))
            # 即使非报单也标记为已识别，避免启动时重复触发
            _mark_msg_recognized(msg_log_id)
            return

        logger.info("媒体接单: 智能体1判定为报单 room=%s log_id=%d complete=%s missing=%s reason=%s",
                     room_id, msg_log_id, validation.get("is_complete"),
                     validation.get("missing_fields"), validation.get("reason"))

        # 信息不完整时提醒客户补充
        if not validation.get("is_complete"):
            missing = validation.get("missing_fields") or []
            missing_str = "、".join(missing) if missing else "部分信息"
            db = SessionLocal()
            try:
                await send_room_at(db, room_id,
                    f"📋 检测到报货信息，但缺少：{missing_str}，请补充完整后重新发送",
                    at_list=[sender_id])
            finally:
                db.close()
            return

        # 3. 验证通过后，图片上传 OSS（仅通义千问支持，其他供应商直接使用 base64）
        if message_type == "image" and ai_input.get("base64"):
            db = SessionLocal()
            try:
                if ai_order_parser.supports_oss_upload(db):
                    cfg = ai_order_parser._load_config(db)
                    vision_model = cfg.get("vision_model") or cfg.get("model") or "qwen3.5-flash"
                    img_bytes = base64.b64decode(ai_input["base64"])
                    ext = (ai_input.get("mime") or "image/png").split("/")[-1]
                    fname = f"media_order_{msg_log_id}.{ext}"
                    oss_url = await ai_order_parser.upload_file(img_bytes, fname, vision_model, db=db)
                    ai_input["oss_url"] = oss_url
                    logger.info("媒体接单: 图片已上传 OSS: %s", oss_url)
                else:
                    logger.info("媒体接单: 当前供应商不支持 OSS 上传，使用 base64 传图")
            except Exception as upload_exc:
                logger.warning("媒体接单: 图片上传 OSS 失败，回退 base64: %s", upload_exc)
            finally:
                db.close()

        # 4. 智能体2：完整解析
        await _process_order(
            [ai_input], customer, room_id, sender_id, instance_id, msg_log_id,
            source_label="媒体接单",
        )
        # 解析完成，标记消息已识别
        _mark_msg_recognized(msg_log_id)

    except Exception as exc:
        logger.exception("媒体接单: 未知错误 room=%s log_id=%d: %s", room_id, msg_log_id, exc)


# ---------------------------------------------------------------------------
# 启动时补扫未识别的消息（图片/文件 + @bot）
# ---------------------------------------------------------------------------
def _restore_payload(msg: dict[str, Any]) -> dict[str, Any]:
    """从 message_logs 行恢复原始 payload dict"""
    payload_str = msg.get("payload_json") or msg.get("payload") or "{}"
    if isinstance(payload_str, str):
        try:
            return json.loads(payload_str)
        except Exception:
            return {}
    return payload_str if isinstance(payload_str, dict) else {}


async def rescan_unrecognized_messages() -> None:
    """扫描最近未被 AI 识别的图片/文件消息和 @bot 消息，重新触发识别流程。"""
    from app.services.message_logs import get_unrecognized_media_messages, get_unrecognized_at_messages, increment_rescan_count

    db = SessionLocal()
    try:
        pending_media = get_unrecognized_media_messages(db, limit=15)
        pending_at = get_unrecognized_at_messages(db, limit=15)
    finally:
        db.close()

    # --- 补扫图片/文件消息 ---
    if pending_media:
        logger.info("[启动补扫] 发现 %d 条未识别的图片/文件消息", len(pending_media))
        for msg in pending_media:
            msg_id = msg.get("id") or 0
            room_id = str(msg.get("room_id") or "").strip()
            sender_id = str(msg.get("sender_id") or "").strip()
            instance_id = str(msg.get("instance_id") or "").strip()
            message_type = str(msg.get("message_type") or "").lower()

            if not room_id:
                _mark_msg_recognized(msg_id)
                continue

            payload = _restore_payload(msg)
            if not payload:
                _mark_msg_recognized(msg_id)
                continue

            db2 = SessionLocal()
            try:
                customer = resolve_customer_by_room(db2, room_id, instance_id)
            finally:
                db2.close()

            if not customer:
                # 不是客户群 → 检查是否为发货群
                from app.services.shipping_scan_handler import resolve_shipping_room, handle_shipping_scan
                db3 = SessionLocal()
                try:
                    shipping_room = resolve_shipping_room(db3, room_id)
                finally:
                    db3.close()

                if shipping_room and message_type in ("image", "img", "picture"):
                    # 递增重试计数，超过2次不再重试
                    db_cnt = SessionLocal()
                    try:
                        count = increment_rescan_count(db_cnt, msg_id)
                    finally:
                        db_cnt.close()
                    if count > 2:
                        logger.info("[启动补扫] 发货扫码已重试%d次，放弃 id=%d", count, msg_id)
                        _mark_msg_recognized(msg_id)
                        # 通知群：已放弃
                        from app.services.shipping_scan_handler import _notify_scan_failure
                        asyncio.create_task(_notify_scan_failure(
                            room_id, sender_id, msg_id,
                            f"多次补扫仍识别失败，已放弃 (重试{count}次)", instance_id,
                        ))
                    else:
                        logger.info("[启动补扫] 重新触发发货扫码 id=%d room=%s (第%d次)", msg_id, room_id, count)
                        asyncio.create_task(handle_shipping_scan(
                            room_id=room_id,
                            sender_id=sender_id,
                            msg_log_id=msg_id,
                            instance_id=instance_id,
                            payload=payload,
                        ))
                else:
                    logger.info("[启动补扫] 跳过媒体 id=%d: room=%s 无绑定客户也非发货群", msg_id, room_id)
                    _mark_msg_recognized(msg_id)
                continue

            logger.info("[启动补扫] 重新触发媒体 id=%d room=%s type=%s", msg_id, room_id, message_type)
            asyncio.create_task(handle_media_order(
                room_id=room_id,
                sender_id=sender_id,
                customer=dict(customer),
                msg_log_id=msg_id,
                instance_id=instance_id,
                payload=payload,
                message_type=message_type if message_type in ("image", "file") else "image",
            ))
    else:
        logger.info("[启动补扫] 没有未识别的图片/文件消息")

    # --- 补扫 @bot 消息 ---
    if pending_at:
        logger.info("[启动补扫] 发现 %d 条未识别的 @bot 消息", len(pending_at))
        for msg in pending_at:
            msg_id = msg.get("id") or 0
            room_id = str(msg.get("room_id") or "").strip()
            sender_id = str(msg.get("sender_id") or "").strip()
            instance_id = str(msg.get("instance_id") or "").strip()
            content = str(msg.get("content_preview") or "").strip()

            if not room_id or not content:
                _mark_msg_recognized(msg_id)
                continue

            payload = _restore_payload(msg)
            # 从 payload 提取触发信息
            trigger_info = extract_trigger_info(payload, instance_id)
            trigger_content = trigger_info.get("content") or content

            if not trigger_content.strip():
                _mark_msg_recognized(msg_id)
                continue

            db2 = SessionLocal()
            try:
                customer = resolve_customer_by_room(db2, room_id, instance_id)
            finally:
                db2.close()

            if not customer:
                logger.info("[启动补扫] 跳过@消息 id=%d: room=%s 无绑定客户", msg_id, room_id)
                _mark_msg_recognized(msg_id)
                continue

            logger.info("[启动补扫] 重新触发@消息 id=%d room=%s content=%s", msg_id, room_id, trigger_content[:50])
            asyncio.create_task(handle_at_order(
                room_id=room_id,
                sender_id=sender_id,
                customer=dict(customer),
                trigger_msg_id=msg_id,
                instance_id=instance_id,
                trigger_content=trigger_content,
            ))
    else:
        logger.info("[启动补扫] 没有未识别的 @bot 消息")
