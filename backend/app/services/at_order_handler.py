"""
群聊 @机器人 自动接单处理器
- 检测 @机器人
- 滑动窗口采集同一 sender 的上下文消息
- 调用 AI 批量解析
- 写入审核队列
- 群内自动回复
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

from app.database import SessionLocal

from app.services.ai_order_parser import AIOrderParserError, ai_order_parser
from app.services.downstream_orders import (
    _normalize_order,
    ensure_review_state,
    resolve_customer_by_room,
)
from app.services.downstream_support import ensure_downstream_support_tables
from app.services.wechat_reply import send_room_at

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 配置常量（可从 ai_config 表或 .env 覆盖）
# ---------------------------------------------------------------------------
AT_ORDER_LOOKBACK_SECONDS = 300   # 向上回溯 5 分钟
AT_ORDER_LOOKBACK_MAX = 20        # 最多回溯 20 条
AT_ORDER_IDLE_TIMEOUT = 15        # 滑动窗口空闲 15 秒
AT_ORDER_MAX_WAIT = 120           # 最长等待 2 分钟
AT_ORDER_POLL_INTERVAL = 2        # 轮询间隔 2 秒

# 报单关键词列表——消息必须包含其中之一才触发接单流程
ORDER_KEYWORDS = [
    "报单", "我要报单", "报货", "我要报货", "下单", "我要下单",
    "订货", "我要订货", "补单", "补货", "加单",
]


def contains_order_keyword(text: str) -> bool:
    """检测文本是否包含报单关键词"""
    if not text:
        return False
    text_lower = text.strip()
    return any(kw in text_lower for kw in ORDER_KEYWORDS)


# 正在采集中的 (room_id, sender_id) → 启动时间，防重复触发
_active_sessions: dict[tuple[str, str], float] = {}

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
def is_at_bot(payload: dict[str, Any], bot_wxid: str) -> bool:
    """检测消息是否 @了机器人"""
    if not bot_wxid:
        return False
    message = payload.get("message") if isinstance(payload.get("message"), dict) else {}
    message_data = message.get("data") if isinstance(message.get("data"), dict) else {}
    if not message_data and isinstance(payload.get("data"), dict):
        message_data = payload["data"]

    # 方式 1: at_list 包含 bot wxid
    at_list = message_data.get("at_list") or payload.get("at_list") or []
    if isinstance(at_list, str):
        try:
            at_list = json.loads(at_list)
        except Exception:
            at_list = [at_list]
    if isinstance(at_list, list) and bot_wxid in at_list:
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
# 滑动窗口采集
# ---------------------------------------------------------------------------
def _query_history_messages(
    db: Session, room_id: str, sender_id: str, lookback_seconds: int, limit: int
) -> list[dict[str, Any]]:
    """向上回溯 message_logs，同一 room_id + sender_id"""
    since = (datetime.now() - timedelta(seconds=lookback_seconds)).strftime("%Y-%m-%d %H:%M:%S")
    rows = db.execute(
        text(
            "SELECT id, message_type, content_preview, payload_json, created_at "
            "FROM message_logs "
            "WHERE room_id = :room_id AND sender_id = :sender_id AND created_at >= :since "
            "ORDER BY created_at ASC LIMIT :limit"
        ),
        {"room_id": room_id, "sender_id": sender_id, "since": since, "limit": limit},
    ).mappings().all()
    return [dict(r) for r in rows]


def _query_new_messages(
    db: Session, room_id: str, sender_id: str, after_id: int, exclude_ids: set[int]
) -> list[dict[str, Any]]:
    """查询 message_logs 中 id > after_id 的新消息（同一 sender）"""
    rows = db.execute(
        text(
            "SELECT id, message_type, content_preview, payload_json, created_at "
            "FROM message_logs "
            "WHERE room_id = :room_id AND sender_id = :sender_id AND id > :after_id "
            "ORDER BY created_at ASC LIMIT 50"
        ),
        {"room_id": room_id, "sender_id": sender_id, "after_id": after_id},
    ).mappings().all()
    return [dict(r) for r in rows if r["id"] not in exclude_ids]


async def _collect_context(
    room_id: str, sender_id: str, trigger_msg_id: int
) -> list[dict[str, Any]]:
    """滑动窗口采集同一 sender 的上下文消息"""
    collected: list[dict[str, Any]] = []
    collected_ids: set[int] = set()

    db = SessionLocal()
    try:
        # 1. 向上回溯
        history = _query_history_messages(db, room_id, sender_id, AT_ORDER_LOOKBACK_SECONDS, AT_ORDER_LOOKBACK_MAX)
        for msg in history:
            if msg["id"] not in collected_ids:
                collected.append(msg)
                collected_ids.add(msg["id"])
    finally:
        db.close()

    # 2. 滑动窗口向下等待
    start_time = time.monotonic()
    last_msg_time = time.monotonic()
    max_seen_id = trigger_msg_id

    while True:
        elapsed = time.monotonic() - start_time
        idle = time.monotonic() - last_msg_time

        if elapsed > AT_ORDER_MAX_WAIT:
            logger.info("@采集窗口: 达到总时限 %ds，room=%s sender=%s", AT_ORDER_MAX_WAIT, room_id, sender_id)
            break
        if idle > AT_ORDER_IDLE_TIMEOUT:
            logger.info("@采集窗口: 空闲超时 %ds，room=%s sender=%s", AT_ORDER_IDLE_TIMEOUT, room_id, sender_id)
            break

        await asyncio.sleep(AT_ORDER_POLL_INTERVAL)

        db = SessionLocal()
        try:
            new_msgs = _query_new_messages(db, room_id, sender_id, max_seen_id, collected_ids)
        finally:
            db.close()

        if new_msgs:
            for msg in new_msgs:
                collected.append(msg)
                collected_ids.add(msg["id"])
                if msg["id"] > max_seen_id:
                    max_seen_id = msg["id"]
            last_msg_time = time.monotonic()
            logger.info("@采集窗口: 新增 %d 条消息，room=%s sender=%s", len(new_msgs), room_id, sender_id)

    return collected


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

    if msg_type in ("text",):
        return {"type": "text", "content": content}

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
        return {"type": "image", "base64": img_b64, "mime": mime, "content": content, "_payload": payload, "_msg_id": msg.get("id")}

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
        return {"type": "file", "file_name": file_name, "content": content, "_payload": payload, "_msg_id": msg.get("id")}

    return {"type": "text", "content": content}


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

        if not save_path.is_file():
            logger.warning("附件下载: 文件未出现 %s", save_path)
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
        elif msg_type == "image" and msg.get("base64"):
            mime = msg.get("mime") or "image/png"
            user_parts.append({"type": "text", "text": f"[消息{idx}] 图片:"})
            user_parts.append({"type": "image_url", "image_url": {"url": msg['base64']}})
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
) -> int:
    """写入 downstream_order_reviews 表"""
    ensure_review_state(db)
    result = db.execute(
        text(
            "INSERT INTO downstream_order_reviews ("
            "source_type, instance_id, room_id, sender_id, message_type, content_text, "
            "parse_status, review_status, customer_id, customer_name, "
            "parsed_order_json, ai_error"
            ") VALUES ("
            "'wechat_at_order', :instance_id, :room_id, :sender_id, 'batch', :content_text, "
            ":parse_status, 'pending', :customer_id, :customer_name, "
            ":parsed_order_json, :ai_error"
            ")"
        ),
        {
            "instance_id": instance_id,
            "room_id": room_id,
            "sender_id": sender_id,
            "content_text": context_summary,
            "parse_status": parse_status,
            "customer_id": customer.get("id"),
            "customer_name": customer.get("customer_name") or "",
            "parsed_order_json": json.dumps(parsed_order, ensure_ascii=False) if parsed_order else None,
            "ai_error": ai_error,
        },
    )
    db.commit()
    return result.lastrowid


# ---------------------------------------------------------------------------
# 主入口
# ---------------------------------------------------------------------------
async def handle_at_order(
    room_id: str,
    sender_id: str,
    customer: dict[str, Any],
    trigger_msg_id: int,
    instance_id: str = "",
) -> None:
    """@机器人 触发后的完整处理流程（异步任务）"""
    session_key = (room_id, sender_id)

    # 防重复
    now = time.monotonic()
    if session_key in _active_sessions:
        if now - _active_sessions[session_key] < AT_ORDER_MAX_WAIT:
            logger.info("@接单: 已有活跃采集会话 room=%s sender=%s，跳过", room_id, sender_id)
            return
    _active_sessions[session_key] = now

    try:
        logger.info("@接单: 开始处理 room=%s sender=%s customer=%s", room_id, sender_id, customer.get("customer_name"))

        # 1. 群内回复「已收到」
        db = SessionLocal()
        try:
            await send_room_at(db, room_id, "📋 已收到下单消息，正在解析中...", at_list=[sender_id])
        finally:
            db.close()

        # 2. 滑动窗口采集上下文
        collected_msgs = await _collect_context(room_id, sender_id, trigger_msg_id)
        if not collected_msgs:
            logger.warning("@接单: 未采集到任何消息 room=%s sender=%s", room_id, sender_id)
            return

        logger.info("@接单: 采集到 %d 条消息 room=%s sender=%s", len(collected_msgs), room_id, sender_id)

        # 3. 转换为 AI 输入格式
        ai_inputs = [_msg_to_ai_input(msg) for msg in collected_msgs]

        # 4. 下载需要的附件（图片/文件）
        db = SessionLocal()
        try:
            for inp in ai_inputs:
                if inp.get("type") in ("image", "file") and not inp.get("base64"):
                    await _download_attachment_for_msg(db, inp, room_id, instance_id)
        finally:
            db.close()

        # 清理内部字段
        for inp in ai_inputs:
            inp.pop("_payload", None)
            inp.pop("_msg_id", None)

        # 过滤无内容的消息
        valid_inputs = [
            inp for inp in ai_inputs
            if inp.get("content") or inp.get("base64") or inp.get("excel_summary")
        ]
        if not valid_inputs:
            logger.warning("@接单: 无有效消息内容 room=%s sender=%s", room_id, sender_id)
            return

        # 5. AI 第一次解析
        context_summary = _build_context_summary(valid_inputs)
        customer_hint = customer.get("customer_name") or ""

        db = SessionLocal()
        try:
            parsed = await ai_order_parser.parse_batch(valid_inputs, customer_hint=customer_hint, db=db)
            normalized = _normalize_order(parsed, customer_hint)
            logger.info("@接单: 第一次解析完成 room=%s items=%d", room_id, len(normalized.get("items") or []))

            # 6. 库存校验：货号+颜色+尺码
            from app.services.erp_sync import ensure_tables
            ensure_tables(db)
            validation = validate_order_against_inventory(db, normalized)

            final_order = normalized
            if not validation["all_valid"]:
                logger.info("@接单: 库存校验未通过，启动二次解析 room=%s", room_id)
                try:
                    reparsed = await reparse_with_product_hints(
                        valid_inputs, normalized, validation,
                        customer_hint=customer_hint, db=db,
                    )
                    final_order = _normalize_order(reparsed, customer_hint)
                    logger.info("@接单: 二次解析完成 room=%s items=%d", room_id, len(final_order.get("items") or []))
                except Exception as reparse_exc:
                    logger.warning("@接单: 二次解析失败，使用第一次结果 room=%s: %s", room_id, reparse_exc)
            else:
                logger.info("@接单: 库存校验全部通过 room=%s", room_id)

            # 7. 写入审核队列
            review_id = _write_review(
                db, final_order, customer, room_id, sender_id, instance_id, context_summary,
                parse_status="success",
            )

            # 8. 写入 at_order_contexts
            ensure_at_order_tables(db)
            collected_ids = [msg["id"] for msg in collected_msgs]
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
                    "context_message_ids": json.dumps(collected_ids),
                    "context_summary": context_summary[:2000],
                    "review_id": review_id,
                },
            )
            db.commit()

            # 9. 群内回复解析结果
            items = final_order.get("items") or []
            total_qty = sum(sum(s.get("qty", 0) for s in it.get("sizes", [])) for it in items)
            product_list = ", ".join(it.get("product_no", "?") for it in items[:5])
            if len(items) > 5:
                product_list += f"...等{len(items)}款"
            reply = f"✅ 订单已识别：{product_list} 共{total_qty}件，已提交审核，请等待确认"
            await send_room_at(db, room_id, reply, at_list=[sender_id])

        except (AIOrderParserError, Exception) as exc:
            logger.error("@接单: AI 解析失败 room=%s sender=%s: %s", room_id, sender_id, exc)
            # 写入失败记录
            _write_review(
                db, {}, customer, room_id, sender_id, instance_id, context_summary,
                parse_status="failed", ai_error=str(exc),
            )
            ensure_at_order_tables(db)
            collected_ids = [msg["id"] for msg in collected_msgs]
            db.execute(
                text(
                    "INSERT INTO at_order_contexts ("
                    "room_id, sender_id, customer_id, customer_name, instance_id, "
                    "trigger_message_id, context_message_ids, context_summary, status, error_message"
                    ") VALUES ("
                    ":room_id, :sender_id, :customer_id, :customer_name, :instance_id, "
                    ":trigger_message_id, :context_message_ids, :context_summary, 'failed', :error_message"
                    ")"
                ),
                {
                    "room_id": room_id,
                    "sender_id": sender_id,
                    "customer_id": customer.get("id"),
                    "customer_name": customer.get("customer_name") or "",
                    "instance_id": instance_id,
                    "trigger_message_id": trigger_msg_id,
                    "context_message_ids": json.dumps(collected_ids),
                    "context_summary": context_summary[:2000],
                    "error_message": str(exc)[:2000],
                },
            )
            db.commit()
            await send_room_at(db, room_id, "⚠️ 无法识别订单内容，请重新发送或联系客服", at_list=[sender_id])
        finally:
            db.close()

    except Exception as exc:
        logger.exception("@接单: 未知错误 room=%s sender=%s: %s", room_id, sender_id, exc)
    finally:
        _active_sessions.pop(session_key, None)
