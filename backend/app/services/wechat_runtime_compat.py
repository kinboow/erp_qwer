import asyncio
import json
import logging
import time
from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.services.downstream_orders import resolve_customer_by_room, _extract_callback_message
from app.services.media_archive import download_and_archive_background
from app.services.message_logs import mark_recalled, record_message_log
from app.services.at_order_handler import is_at_bot
from app.services.shipping_scan_handler import handle_shipping_scan, resolve_shipping_room
from app.services.ai_chat_service import process_customer_group_message

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 客户群消息：缓冲 → 延迟 → 批量送入 AI 对话
# ---------------------------------------------------------------------------
AI_BUFFER_DELAY_SECONDS = 120  # 缓冲 2 分钟再送 AI

# room_id → {"messages": [...], "task": asyncio.Task | None, "last_ts": float}
_room_buffers: dict[str, dict[str, Any]] = {}

# message_server_id → room_id  用于撤回时从 buffer 中移除
_server_id_to_room: dict[str, str] = {}

# message_server_id → asyncio.Task  （旧字段，兼容撤回检测）
_pending_delayed_tasks: dict[str, asyncio.Task] = {}




def _handle_recall(db: Session, normalized_payload: dict, resolved_instance_id: str) -> bool:
    """检测并处理撤回消息（type=11123）。返回 True 表示本消息是撤回事件并已处理。"""
    message = normalized_payload.get("message") if isinstance(normalized_payload.get("message"), dict) else {}
    msg_type = message.get("type")
    # 也兼容顶层 type
    if msg_type is None:
        msg_type = normalized_payload.get("type")
    try:
        msg_type = int(msg_type)
    except (TypeError, ValueError):
        return False

    if msg_type != 11123:
        return False

    msg_data = message.get("data") if isinstance(message.get("data"), dict) else {}
    if not msg_data:
        msg_data = normalized_payload.get("data") if isinstance(normalized_payload.get("data"), dict) else {}

    recalled_server_id = str(msg_data.get("message_server_id") or "").strip()
    recall_room_id = str(msg_data.get("room_id") or msg_data.get("room_wxid") or "").strip()

    if not recalled_server_id:
        logger.info("撤回消息: 无 message_server_id，跳过")
        return True

    logger.info("撤回消息: 检测到 server_id=%s room=%s", recalled_server_id, recall_room_id)

    # 标记数据库中的原始消息为已撤回
    recalled_msg_id = mark_recalled(db, recalled_server_id, recall_room_id)
    if recalled_msg_id:
        logger.info("撤回消息: 已标记 msg_log_id=%d server_id=%s", recalled_msg_id, recalled_server_id)
    else:
        logger.info("撤回消息: 未找到对应原始消息 server_id=%s", recalled_server_id)

    # 从缓冲区中移除已撤回的消息
    buf_room = _server_id_to_room.pop(recalled_server_id, None)
    if buf_room and buf_room in _room_buffers:
        buf = _room_buffers[buf_room]
        buf["messages"] = [m for m in buf["messages"] if m.get("server_id") != recalled_server_id]
        logger.info("撤回消息: 已从缓冲区移除 server_id=%s room=%s remaining=%d",
                     recalled_server_id, buf_room, len(buf["messages"]))

    # 取消延迟任务
    pending_task = _pending_delayed_tasks.pop(recalled_server_id, None)
    if pending_task and not pending_task.done():
        pending_task.cancel()
        logger.info("撤回消息: 已取消延迟任务 server_id=%s", recalled_server_id)

    return True


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

    # 解析 instance_id：优先用传入参数，再从 payload body 取，最后根据 wxid 查 DB
    _raw_instance_id = _safe_text(instance_id) or _safe_text(normalized_payload.get("instanceId")) or ""
    # 如果传入的 instance_id 看起来是 wxid（长度 > 10 的纯数字），需要查 DB 转成实际的 DB id
    if _raw_instance_id and len(_raw_instance_id) > 10 and _raw_instance_id.isdigit():
        resolved_instance_id = resolve_instance_id_by_wxid(db, _raw_instance_id) or _raw_instance_id
    elif _raw_instance_id:
        resolved_instance_id = _raw_instance_id
    else:
        resolved_instance_id = resolve_instance_id_by_wxid(db, effective_wxid) or ""

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

    # ===== 撤回消息检测：type=11123 → 标记原消息已撤回 + 取消延迟任务 =====
    if _handle_recall(db, normalized_payload, resolved_instance_id):
        return {
            "instanceId": resolved_instance_id,
            "wxid": effective_wxid or _safe_text(normalized_payload.get("wxid")),
            "received": True,
            "log": log_result,
            "review": None,
            "at_order_triggered": False,
            "media_order_triggered": False,
            "shipping_scan_triggered": False,
            "recall_handled": True,
        }

    # 图片/文件消息自动归档到 OSS
    if log_result:
        _log_msg_type = str(log_result.get("message_type") or "").lower()
        if _log_msg_type in ("image", "img", "picture", "file"):
            _msg_data = (normalized_payload.get("message") or {}).get("data") or normalized_payload.get("data") or {}
            if isinstance(_msg_data, str):
                _msg_data = {}
            _file_name = str(
                _msg_data.get("file_name") or _msg_data.get("filename")
                or normalized_payload.get("file_name") or normalized_payload.get("filename")
                or log_result.get("content_preview") or ""
            )
            asyncio.create_task(download_and_archive_background(
                msg_log_id=log_result["id"],
                payload=normalized_payload,
                instance_id=resolved_instance_id or effective_wxid or "",
                message_type=_log_msg_type,
                file_name=_file_name,
            ))
            logger.debug("媒体归档: 已创建后台任务 msg_log_id=%s type=%s", log_result["id"], _log_msg_type)

    # 检查发送者是否为员工账号——如果是则跳过订单处理，仅保留日志
    sender_is_employee = False
    _sender_id = ""
    try:
        _sender_id = _safe_text(
            (normalized_payload.get("message") or {}).get("data", {}).get("sender")
            or (normalized_payload.get("data") or {}).get("sender")
            or normalized_payload.get("sender_id")
            or normalized_payload.get("from_wxid")
            or (normalized_payload.get("message") or {}).get("data", {}).get("from_wxid")
        )
        if _sender_id:
            _emp_row = db.execute(
                text("SELECT 1 FROM wechat_employee_accounts WHERE wxid = :wxid LIMIT 1"),
                {"wxid": _sender_id},
            ).first()
            sender_is_employee = _emp_row is not None
    except Exception:
        pass

    room_id = str((log_result or {}).get("room_id") or "").strip()
    log_msg_type = str((log_result or {}).get("message_type") or "").lower()
    log_sender_id = str((log_result or {}).get("sender_id") or _sender_id or "").strip()

    logger.info("消息分流诊断: room_id=%r msg_type=%r sender=%r instance=%r employee=%r log_ok=%s",
                room_id, log_msg_type, log_sender_id, resolved_instance_id,
                sender_is_employee, log_result is not None)

    shipping_room = None
    customer = None
    if room_id:
        try:
            shipping_room = resolve_shipping_room(db, room_id)
        except Exception as _e:
            logger.warning("resolve_shipping_room 异常: room=%s err=%s", room_id, _e)
            shipping_room = None
        try:
            customer = resolve_customer_by_room(db, room_id, resolved_instance_id)
        except Exception as _e:
            logger.warning("resolve_customer_by_room 异常: room=%s instance=%s err=%s", room_id, resolved_instance_id, _e)
            customer = None
        logger.info("消息分流结果: room=%s → shipping_room=%s customer=%s",
                    room_id, shipping_room is not None, customer.get("customer_name") if customer else None)
    else:
        logger.warning("消息分流: room_id 为空，无法分流。log_result=%s", log_result)

    # ===== 发货群专线：只走发货扫码/发货AI，不进入客户群审核链 =====
    # 不受 sender_is_employee 限制，员工也可能转发发货单图片
    shipping_scan_triggered = False
    try:
        if shipping_room and log_msg_type in ("image", "img", "picture") and room_id:
            logger.info("发货扫码检测: resolve_shipping_room(%s) → %s", room_id, shipping_room)
            _log_id_early = (log_result or {}).get("id") or 0
            if _log_id_early:
                asyncio.create_task(handle_shipping_scan(
                    room_id=room_id,
                    sender_id=log_sender_id,
                    msg_log_id=_log_id_early,
                    instance_id=resolved_instance_id,
                    payload=normalized_payload,
                ))
                shipping_scan_triggered = True
                logger.info("发货扫码: 已触发 room=%s sender=%s log_id=%d",
                            room_id, log_sender_id, _log_id_early)
    except Exception as exc:
        logger.warning("发货扫码检测异常: %s", exc, exc_info=True)

    # 发货群全部消息都不进入客户群审核/接单流程
    if shipping_room:
        return {
            "instanceId": resolved_instance_id,
            "wxid": effective_wxid or _safe_text(normalized_payload.get("wxid")),
            "received": True,
            "log": log_result,
            "review": None,
            "at_order_triggered": False,
            "media_order_triggered": False,
            "shipping_scan_triggered": shipping_scan_triggered,
        }

    # ===== 客户群专线：缓冲消息 → 延迟 → 批量送 AI =====
    ai_chat_result = None

    if not customer:
        logger.info("客户群专线跳过: customer 未找到 room=%s instance=%s", room_id, resolved_instance_id)
    elif sender_is_employee:
        logger.info("客户群专线跳过: 发送者是员工 sender=%s room=%s", log_sender_id, room_id)

    if customer and not sender_is_employee:
        bot_wxid = effective_wxid or _safe_text(normalized_payload.get("wxid"))

        # ---- 过滤：机器人自身发送的消息不送 AI ----
        if log_sender_id and bot_wxid and log_sender_id == bot_wxid:
            logger.info("客户群: 跳过机器人自身消息 sender=%s room=%s", log_sender_id, room_id)
            return {
                "instanceId": resolved_instance_id,
                "wxid": bot_wxid,
                "received": True, "log": log_result,
                "ai_chat": None, "shipping_scan_triggered": False,
                "skipped": "bot_self_message",
            }

        # ---- 过滤：非图片且非 Excel 的文件不送 AI ----
        if log_msg_type == "file":
            _fn = str((log_result or {}).get("content_preview") or "").lower()
            if not (_fn.endswith(".xlsx") or _fn.endswith(".xls")):
                logger.info("客户群: 跳过非 Excel 文件 file=%s room=%s", _fn, room_id)
                return {
                    "instanceId": resolved_instance_id,
                    "wxid": bot_wxid,
                    "received": True, "log": log_result,
                    "ai_chat": None, "shipping_scan_triggered": False,
                    "skipped": "non_excel_file",
                }

        # 标记 @bot 消息（保留，用于日志分析）
        if (bot_wxid or resolved_instance_id) and is_at_bot(normalized_payload, bot_wxid, resolved_instance_id):
            _log_id = (log_result or {}).get("id")
            if _log_id:
                try:
                    db.execute(text("UPDATE message_logs SET is_at_bot = 1 WHERE id = :id"), {"id": _log_id})
                    db.commit()
                except Exception:
                    pass

        # ---- 提取消息内容 ----
        _extracted = _extract_callback_message(normalized_payload, resolved_instance_id or None)
        _content_text = (_extracted.get("content_text") or "").strip()
        _sender_name = str((log_result or {}).get("sender_name") or _extracted.get("sender_name") or "").strip()
        _attachment_base64 = _extracted.get("attachment_base64") or ""
        _file_name = _extracted.get("attachment_name") or ""

        # 提取 message_server_id 用于撤回追踪
        _msg_data = (normalized_payload.get("message") or {}).get("data") or normalized_payload.get("data") or {}
        if isinstance(_msg_data, str):
            _msg_data = {}
        _server_id = str(_msg_data.get("message_server_id") or "").strip()

        # ---- 放入缓冲区，延迟 2 分钟后统一送 AI ----
        msg_entry = {
            "server_id": _server_id,
            "room_id": room_id,
            "sender_id": log_sender_id,
            "sender_name": _sender_name,
            "message_type": log_msg_type,
            "content_text": _content_text,
            "attachment_base64": _attachment_base64,
            "file_name": _file_name,
            "customer": dict(customer) if customer else None,
            "instance_id": resolved_instance_id or "",
            "bot_wxid": bot_wxid or "",
            "payload": normalized_payload,
            "log_id": (log_result or {}).get("id"),
        }

        if _server_id:
            _server_id_to_room[_server_id] = room_id

        _enqueue_message(room_id, msg_entry)

        return {
            "instanceId": resolved_instance_id,
            "wxid": bot_wxid,
            "received": True,
            "log": log_result,
            "ai_chat": "buffered",
            "shipping_scan_triggered": False,
        }

    # ===== 其他群 / 未分类群：不处理、不回复，仅记录日志 =====
    logger.debug("未分类群消息，跳过处理 room=%s", room_id)

    return {
        "instanceId": resolved_instance_id,
        "wxid": effective_wxid or _safe_text(normalized_payload.get("wxid")),
        "received": True,
        "log": log_result,
        "review": None,
        "at_order_triggered": False,
        "media_order_triggered": False,
        "shipping_scan_triggered": shipping_scan_triggered,
    }


# ---------------------------------------------------------------------------
# 客户群消息缓冲：延迟 2 分钟，收集完整批量送 AI
# ---------------------------------------------------------------------------
def _enqueue_message(room_id: str, msg_entry: dict[str, Any]) -> None:
    """将消息放入 room 缓冲区，启动/重置延迟任务。"""
    now = time.monotonic()
    if room_id not in _room_buffers:
        _room_buffers[room_id] = {"messages": [], "task": None, "first_ts": now}

    buf = _room_buffers[room_id]
    buf["messages"].append(msg_entry)
    buf["last_ts"] = now

    # 如果已有延迟任务在等待，不需要重新创建（到时间后会 flush 所有积攒的消息）
    if buf.get("task") and not buf["task"].done():
        logger.debug("客户群缓冲: 追加消息到 room=%s buffer_size=%d", room_id, len(buf["messages"]))
        return

    # 创建新的延迟任务
    buf["task"] = asyncio.create_task(_delayed_flush(room_id))
    logger.info("客户群缓冲: 新建延迟任务 room=%s delay=%ds", room_id, AI_BUFFER_DELAY_SECONDS)


async def _delayed_flush(room_id: str) -> None:
    """等待延迟时间后，将缓冲区消息批量送 AI。"""
    try:
        await asyncio.sleep(AI_BUFFER_DELAY_SECONDS)
    except asyncio.CancelledError:
        logger.info("客户群缓冲: 延迟任务被取消 room=%s", room_id)
        return

    buf = _room_buffers.pop(room_id, None)
    if not buf or not buf["messages"]:
        return

    messages = buf["messages"]
    logger.info("客户群缓冲: 开始批量送 AI room=%s count=%d", room_id, len(messages))

    # 逐条送 AI（AI 通过对话历史保持上下文）
    db = SessionLocal()
    try:
        for msg in messages:
            try:
                ai_result = await process_customer_group_message(
                    db,
                    room_id=msg["room_id"],
                    sender_id=msg["sender_id"],
                    sender_name=msg["sender_name"],
                    message_type=msg["message_type"],
                    content_text=msg["content_text"],
                    attachment_base64=msg.get("attachment_base64") or "",
                    file_name=msg.get("file_name") or "",
                    customer=msg.get("customer"),
                    instance_id=msg.get("instance_id") or "",
                    bot_wxid=msg.get("bot_wxid") or "",
                    payload=msg.get("payload"),
                )
                logger.info("客户群 AI 对话: room=%s result=%s", room_id, ai_result)

                # 标记消息已被 AI 处理
                _log_id = msg.get("log_id")
                if _log_id:
                    try:
                        from app.services.message_logs import mark_ai_recognized
                        mark_ai_recognized(db, _log_id)
                    except Exception:
                        pass
            except Exception as exc:
                logger.warning("客户群 AI 对话异常: room=%s err=%s", room_id, exc)
                try:
                    db.rollback()
                except Exception:
                    pass

            # 清理 server_id 映射
            sid = msg.get("server_id")
            if sid:
                _server_id_to_room.pop(sid, None)
    finally:
        db.close()
