import asyncio
import json
import logging
from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.services.downstream_orders import create_review_from_callback, resolve_customer_by_room
from app.services.media_archive import download_and_archive_background
from app.services.message_logs import record_message_log
from app.services.at_order_handler import extract_trigger_info, handle_at_order, handle_media_order, is_at_bot
from app.services.shipping_scan_handler import handle_shipping_scan, resolve_shipping_room

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

    # ===== 发货群图片扫码检测（优先检测，避免被后续慢速 AI 解析阻塞/取消） =====
    # 不受 sender_is_employee 限制，员工也可能转发发货单图片
    shipping_scan_triggered = False
    try:
        _log_msg_type_early = str((log_result or {}).get("message_type") or "").lower()
        _log_room_id_early = str((log_result or {}).get("room_id") or "").strip()
        if _log_msg_type_early in ("image", "img", "picture") and _log_room_id_early:
            from app.database import SessionLocal as _SL
            _scan_db = _SL()
            try:
                shipping_room = resolve_shipping_room(_scan_db, _log_room_id_early)
            finally:
                _scan_db.close()
            logger.info("发货扫码检测: resolve_shipping_room(%s) → %s", _log_room_id_early, shipping_room)
            if shipping_room:
                _log_sender_id_early = str((log_result or {}).get("sender_id") or _sender_id or "").strip()
                _log_id_early = (log_result or {}).get("id") or 0
                asyncio.create_task(handle_shipping_scan(
                    room_id=_log_room_id_early,
                    sender_id=_log_sender_id_early,
                    msg_log_id=_log_id_early,
                    instance_id=resolved_instance_id,
                    payload=normalized_payload,
                ))
                shipping_scan_triggered = True
                logger.info("发货扫码: 已触发 room=%s sender=%s log_id=%d",
                            _log_room_id_early, _log_sender_id_early, _log_id_early)
    except Exception as exc:
        logger.warning("发货扫码检测异常: %s", exc, exc_info=True)

    # 发货群图片已触发扫码，无需走审核/接单流程，立即返回
    if shipping_scan_triggered:
        return {
            "instanceId": resolved_instance_id,
            "wxid": effective_wxid or _safe_text(normalized_payload.get("wxid")),
            "received": True,
            "log": log_result,
            "review": None,
            "at_order_triggered": False,
            "media_order_triggered": False,
            "shipping_scan_triggered": True,
        }

    # ===== 以下为客户群/其他群的处理流程 =====
    review_result = None
    if not sender_is_employee:
        try:
            review_result = await create_review_from_callback(db, normalized_payload, resolved_instance_id or None)
        except Exception as exc:
            logger.warning("create_review_from_callback failed: %s", exc)
            try:
                db.rollback()
            except Exception:
                pass

    # @机器人 自动接单检测（员工消息跳过，不再要求关键词，AI 预判）
    at_order_triggered = False
    media_order_triggered = False
    try:
        bot_wxid = effective_wxid or _safe_text(normalized_payload.get("wxid"))
        if not sender_is_employee and (bot_wxid or resolved_instance_id) and is_at_bot(normalized_payload, bot_wxid, resolved_instance_id):
            # 标记此消息为 @bot 消息
            _log_id = (log_result or {}).get("id")
            if _log_id:
                try:
                    db.execute(text("UPDATE message_logs SET is_at_bot = 1 WHERE id = :id"), {"id": _log_id})
                    db.commit()
                except Exception:
                    pass
            trigger_info = extract_trigger_info(normalized_payload, resolved_instance_id)
            trigger_room_id = trigger_info.get("room_id") or ""
            trigger_sender_id = trigger_info.get("sender_id") or ""
            trigger_content = trigger_info.get("content") or ""
            if trigger_room_id and trigger_sender_id:
                customer = resolve_customer_by_room(db, trigger_room_id, resolved_instance_id)
                if customer:
                    trigger_msg_id = (log_result or {}).get("id") or 0
                    asyncio.create_task(handle_at_order(
                        room_id=trigger_room_id,
                        sender_id=trigger_sender_id,
                        customer=dict(customer),
                        trigger_msg_id=trigger_msg_id,
                        instance_id=trigger_info.get("instance_id") or "",
                        trigger_content=trigger_content,
                    ))
                    at_order_triggered = True
                    logger.info("@接单: 已触发（AI将预判）room=%s sender=%s",
                                trigger_room_id, trigger_sender_id)
    except Exception as exc:
        logger.warning("@接单检测异常: %s", exc)

    # 图片/文件自动接单检测（客户群内非员工消息）
    # 图片：直接触发；文件：仅 Excel（.xlsx/.xls）触发，其余忽略
    if not sender_is_employee and not at_order_triggered:
        try:
            log_msg_type = str((log_result or {}).get("message_type") or "").lower()
            is_image = log_msg_type in ("image", "img", "picture")
            is_file = log_msg_type == "file"

            should_trigger = False
            media_type = "image"
            if is_image:
                should_trigger = True
                media_type = "image"
            elif is_file:
                # 仅 Excel 文件触发，提取文件名判断扩展名
                _content_preview = str((log_result or {}).get("content_preview") or "").lower()
                _msg_data = (normalized_payload.get("message") or {}).get("data") or normalized_payload.get("data") or {}
                if isinstance(_msg_data, str):
                    _msg_data = {}
                _file_name = str(
                    _msg_data.get("file_name") or _msg_data.get("filename")
                    or normalized_payload.get("file_name") or normalized_payload.get("filename")
                    or _content_preview or ""
                ).lower()
                if _file_name.endswith((".xlsx", ".xls")):
                    should_trigger = True
                    media_type = "file"

            if should_trigger:
                log_room_id = str((log_result or {}).get("room_id") or "").strip()
                log_sender_id = str((log_result or {}).get("sender_id") or _sender_id or "").strip()
                if log_room_id:
                    customer = resolve_customer_by_room(db, log_room_id, resolved_instance_id)
                    if customer:
                        log_id = (log_result or {}).get("id") or 0
                        asyncio.create_task(handle_media_order(
                            room_id=log_room_id,
                            sender_id=log_sender_id,
                            customer=dict(customer),
                            msg_log_id=log_id,
                            instance_id=resolved_instance_id,
                            payload=normalized_payload,
                            message_type=media_type,
                        ))
                        media_order_triggered = True
                        logger.info("媒体接单: 已触发（AI将预判）room=%s type=%s",
                                    log_room_id, media_type)
        except Exception as exc:
            logger.warning("媒体接单检测异常: %s", exc)

    return {
        "instanceId": resolved_instance_id,
        "wxid": effective_wxid or _safe_text(normalized_payload.get("wxid")),
        "received": True,
        "log": log_result,
        "review": review_result,
        "at_order_triggered": at_order_triggered,
        "media_order_triggered": media_order_triggered,
        "shipping_scan_triggered": shipping_scan_triggered,
    }
