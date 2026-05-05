import asyncio
import json
import logging
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
# 客户群消息：实时送入 AI 对话
# ---------------------------------------------------------------------------




def _handle_recall(db: Session, normalized_payload: dict, resolved_instance_id: str) -> dict | None:
    """检测并处理撤回消息（type=11123）。

    返回:
        None  — 本消息不是撤回事件
        dict  — 撤回事件的信息，包含原始消息内容等
    """
    message = normalized_payload.get("message") if isinstance(normalized_payload.get("message"), dict) else {}
    msg_type = message.get("type")
    if msg_type is None:
        msg_type = normalized_payload.get("type")
    try:
        msg_type = int(msg_type)
    except (TypeError, ValueError):
        return None

    if msg_type != 11123:
        return None

    msg_data = message.get("data") if isinstance(message.get("data"), dict) else {}
    if not msg_data:
        msg_data = normalized_payload.get("data") if isinstance(normalized_payload.get("data"), dict) else {}

    recalled_server_id = str(msg_data.get("message_server_id") or "").strip()
    recall_room_id = str(msg_data.get("room_id") or msg_data.get("room_wxid") or "").strip()

    if not recalled_server_id:
        logger.info("撤回消息: 无 message_server_id，跳过")
        return {"is_recall": True}

    logger.info("撤回消息: 检测到 server_id=%s room=%s", recalled_server_id, recall_room_id)

    # 先查出原始消息内容（标记撤回前查）
    original_msg = None
    try:
        row = db.execute(
            text(
                "SELECT id, sender_id, sender_name, message_type, content_preview, room_id "
                "FROM message_logs "
                "WHERE message_server_id = :sid AND is_recalled = 0 "
                "ORDER BY id DESC LIMIT 1"
            ),
            {"sid": recalled_server_id},
        ).mappings().first()
        if row:
            original_msg = dict(row)
    except Exception as exc:
        logger.warning("撤回消息: 查询原始消息失败: %s", exc)

    # 标记数据库中的原始消息为已撤回
    recalled_msg_id = mark_recalled(db, recalled_server_id, recall_room_id)
    if recalled_msg_id:
        logger.info("撤回消息: 已标记 msg_log_id=%d server_id=%s", recalled_msg_id, recalled_server_id)
    else:
        logger.info("撤回消息: 未找到对应原始消息 server_id=%s", recalled_server_id)

    return {
        "is_recall": True,
        "recalled_server_id": recalled_server_id,
        "recall_room_id": recall_room_id or (original_msg or {}).get("room_id", ""),
        "original_msg": original_msg,
    }


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

    # ===== 撤回消息检测：type=11123 → 标记原消息已撤回 + 通知 AI =====
    recall_info = _handle_recall(db, normalized_payload, resolved_instance_id)
    if recall_info is not None:
        # 如果有原始消息信息，异步通知 AI 该消息已被撤回
        original = recall_info.get("original_msg")
        _recall_room = recall_info.get("recall_room_id") or ""
        if original and _recall_room:
            _orig_sender = original.get("sender_name") or original.get("sender_id") or ""
            _orig_type = original.get("message_type") or "text"
            _orig_content = original.get("content_preview") or ""
            # 查找该群对应的客户信息
            _recall_customer = None
            try:
                _recall_customer = resolve_customer_by_room(db, _recall_room, resolved_instance_id)
            except Exception:
                pass
            if _recall_customer:
                asyncio.create_task(_send_recall_to_ai(
                    room_id=_recall_room,
                    sender_name=_orig_sender,
                    sender_id=original.get("sender_id") or "",
                    message_type=_orig_type,
                    content_preview=_orig_content,
                    customer=_recall_customer,
                    instance_id=resolved_instance_id or "",
                    bot_wxid=effective_wxid or "",
                ))
        return {
            "instanceId": resolved_instance_id,
            "wxid": effective_wxid or _safe_text(normalized_payload.get("wxid")),
            "received": True,
            "log": log_result,
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

    # ===== 客户群专线：实时送 AI =====
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

        # ---- 立即异步送 AI ----
        asyncio.create_task(_send_msg_to_ai(
            room_id=room_id,
            sender_id=log_sender_id,
            sender_name=_sender_name,
            message_type=log_msg_type,
            content_text=_content_text,
            attachment_base64=_attachment_base64,
            file_name=_file_name,
            customer=dict(customer) if customer else None,
            instance_id=resolved_instance_id or "",
            bot_wxid=bot_wxid or "",
            payload=normalized_payload,
            log_id=(log_result or {}).get("id"),
        ))

        return {
            "instanceId": resolved_instance_id,
            "wxid": bot_wxid,
            "received": True,
            "log": log_result,
            "ai_chat": "dispatched",
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
# 客户群消息：实时送 AI
# ---------------------------------------------------------------------------
async def _send_msg_to_ai(
    *,
    room_id: str,
    sender_id: str,
    sender_name: str,
    message_type: str,
    content_text: str,
    attachment_base64: str,
    file_name: str,
    customer: dict[str, Any] | None,
    instance_id: str,
    bot_wxid: str,
    payload: dict[str, Any] | None,
    log_id: int | None,
) -> None:
    """立即将一条消息送入 AI 对话。"""
    db = SessionLocal()
    try:
        ai_result = await process_customer_group_message(
            db,
            room_id=room_id,
            sender_id=sender_id,
            sender_name=sender_name,
            message_type=message_type,
            content_text=content_text,
            attachment_base64=attachment_base64,
            file_name=file_name,
            customer=customer,
            instance_id=instance_id,
            bot_wxid=bot_wxid,
            payload=payload,
        )
        logger.info("客户群 AI 对话: room=%s result=%s", room_id, ai_result)

        if log_id:
            try:
                from app.services.message_logs import mark_ai_recognized
                mark_ai_recognized(db, log_id)
            except Exception:
                pass
    except Exception as exc:
        logger.warning("客户群 AI 对话异常: room=%s err=%s", room_id, exc)
    finally:
        db.close()


async def _send_recall_to_ai(
    *,
    room_id: str,
    sender_name: str,
    sender_id: str,
    message_type: str,
    content_preview: str,
    customer: dict[str, Any] | None,
    instance_id: str,
    bot_wxid: str,
) -> None:
    """将撤回事件作为一条特殊消息送入 AI 对话，告知原始内容。"""
    # 构造撤回通知文本
    type_label = {"text": "文字", "image": "图片", "file": "文件"}.get(message_type, message_type)
    recall_text = (
        f"[系统通知] {sender_name} 撤回了一条{type_label}消息。"
        f"被撤回的原始内容：{content_preview or '（无法获取）'}"
    )

    db = SessionLocal()
    try:
        ai_result = await process_customer_group_message(
            db,
            room_id=room_id,
            sender_id=sender_id,
            sender_name="系统",
            message_type="text",
            content_text=recall_text,
            customer=customer,
            instance_id=instance_id,
            bot_wxid=bot_wxid,
        )
        logger.info("撤回通知 AI: room=%s result=%s", room_id, ai_result)
    except Exception as exc:
        logger.warning("撤回通知 AI 异常: room=%s err=%s", room_id, exc)
    finally:
        db.close()
