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

        # 5. AI 批量解析
        context_summary = _build_context_summary(valid_inputs)
        customer_hint = customer.get("customer_name") or ""

        db = SessionLocal()
        try:
            parsed = await ai_order_parser.parse_batch(valid_inputs, customer_hint=customer_hint, db=db)
            normalized = _normalize_order(parsed, customer_hint)

            # 6. 写入审核队列
            review_id = _write_review(
                db, normalized, customer, room_id, sender_id, instance_id, context_summary,
                parse_status="success",
            )

            # 7. 写入 at_order_contexts
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

            # 8. 群内回复解析结果
            items = normalized.get("items") or []
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
