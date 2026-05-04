import asyncio
import json
import logging
import time
from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.services.downstream_orders import create_review_from_callback, resolve_customer_by_room, _extract_callback_message
from app.services.media_archive import download_and_archive_background
from app.services.message_logs import mark_recalled, record_message_log
from app.services.ai_order_parser import AIOrderParser
from app.services.at_order_handler import is_at_bot
from app.services.pending_order_session import (
    find_active_session, append_followup_message, get_original_summary,
    create_pending_session, update_session_missing_fields,
    mark_session_completed, get_merged_context, cleanup_expired_sessions,
)
from app.services.shipping_scan_handler import handle_shipping_scan, resolve_shipping_room
from app.services.wechat_reply import send_room_at

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 客户群消息：回复"收到"后走通用审核链 create_review_from_callback
# ---------------------------------------------------------------------------
STARTUP_GRACE_SECONDS = 30   # 启动后多少秒内的消息不回复"收到"（避免积压消息被批量回复）
CLASSIFY_WINDOW_SECONDS = 150  # 订单意图分类：报货后等待 2.5 分钟收集上下文
CLASSIFY_PRE_MSG_COUNT = 10    # 分类时向前取多少条聊天记录

# 模块加载时间（服务启动时）
_startup_time = time.monotonic()

# message_server_id → asyncio.Task  用于撤回时取消延迟任务（保留用于撤回检测）
_pending_delayed_tasks: dict[str, asyncio.Task] = {}


def _is_after_startup() -> bool:
    """判断当前是否已过启动宽限期，只有过了宽限期的消息才回复'收到'"""
    return (time.monotonic() - _startup_time) > STARTUP_GRACE_SECONDS


async def _reply_received(room_id: str, sender_id: str, instance_id: str) -> None:
    """在客户群中回复「收到」（使用独立 DB session）"""
    db = SessionLocal()
    try:
        inst_id = int(instance_id) if instance_id.isdigit() else None
        await send_room_at(db, room_id, "收到",
                           at_list=[sender_id], instance_id=inst_id)
    except Exception as exc:
        logger.warning("回复收到失败: room=%s err=%s", room_id, exc)
    finally:
        db.close()


async def _reply_missing_fields(
    room_id: str, sender_id: str, instance_id: str, missing_fields: list[str],
) -> None:
    """在客户群中@发送人告知缺少哪些字段（使用独立 DB session）"""
    db = SessionLocal()
    try:
        inst_id = int(instance_id) if instance_id.isdigit() else None
        fields_text = "、".join(missing_fields)
        msg = f"您的报货信息缺少以下内容：{fields_text}，请补充后我会继续处理"
        await send_room_at(db, room_id, msg,
                           at_list=[sender_id], instance_id=inst_id)
    except Exception as exc:
        logger.warning("回复缺失字段失败: room=%s err=%s", room_id, exc)
    finally:
        db.close()


async def _handle_pending_session_followup(
    db: Session,
    session: dict[str, Any],
    ctx_msgs: list[dict[str, Any]],
    room_id: str,
    sender_id: str,
    instance_id: str,
    normalized_payload: dict[str, Any],
) -> dict[str, Any]:
    """处理挂起会话的后续消息：调用补全智能体判断是否已补全。

    返回:
        {"handled": True/False, "review": ...}
    """
    session_id = session["id"]
    missing_fields = json.loads(session["missing_fields"]) if isinstance(session["missing_fields"], str) else session["missing_fields"]

    # 追加后续消息到会话
    followup_msg = ctx_msgs[0] if ctx_msgs else {"type": "text", "content": ""}
    all_followups = append_followup_message(db, session_id, followup_msg)
    logger.info("[PendingSession] 追加后续消息 session=%d followup_count=%d", session_id, len(all_followups))

    # 调用补全智能体
    original_summary = get_original_summary(session)
    parser = AIOrderParser()
    try:
        completion_result = await parser.check_completion(
            missing_fields=missing_fields,
            original_summary=original_summary,
            followup_messages=all_followups,
            db=db,
        )
    except Exception as exc:
        logger.warning("[PendingSession] 补全智能体异常: session=%d err=%s", session_id, exc)
        return {"handled": True, "review": None}

    logger.info(
        "[PendingSession] 补全判断 session=%d is_complete=%s still_missing=%s reason=%s",
        session_id, completion_result.get("is_complete"), completion_result.get("still_missing"),
        completion_result.get("reason"),
    )

    if completion_result.get("is_complete"):
        # 已补全 → 标记完成 → 合并上下文走审核链
        mark_session_completed(db, session_id)
        merged_context = get_merged_context(session)
        # 追加当前新消息
        merged_context.extend(ctx_msgs)

        # 回复收到
        if _is_after_startup():
            asyncio.create_task(_reply_received(room_id, sender_id, instance_id))

        # 走审核链
        review_result = await create_review_from_callback(
            db, normalized_payload, instance_id or None,
        )
        logger.info("[PendingSession] 补全后进入审核链 session=%d review=%s",
                    session_id,
                    review_result.get("id") if isinstance(review_result, dict) and not review_result.get("skipped") else "skipped")
        return {"handled": True, "review": review_result}

    # 未补全 → 更新剩余缺失字段
    still_missing = completion_result.get("still_missing") or missing_fields
    if still_missing != missing_fields:
        update_session_missing_fields(db, session_id, still_missing)

    # 如果不是无关消息，不需要再回复
    if not completion_result.get("is_irrelevant"):
        logger.info("[PendingSession] 部分补全但仍缺: %s session=%d", still_missing, session_id)
    return {"handled": True, "review": None}


async def _collect_and_classify_order(
    review_id: int,
    room_id: str,
    trigger_log_id: int,
    trigger_created_at: str,
) -> None:
    """后台任务：等待 2.5 分钟后收集上下文，调用 AI 判断订单意图（new/replace/append）。

    步骤:
    1. 等待 CLASSIFY_WINDOW_SECONDS 秒
    2. 从 message_logs 查询触发消息前的 N 条消息（排除 @bot）
    3. 从 message_logs 查询触发消息后 2.5 分钟内的所有消息
    4. 合并上下文 → 调用 classify_order AI
    5. 将结果写入 downstream_order_reviews.order_intent
    """
    await asyncio.sleep(CLASSIFY_WINDOW_SECONDS)

    db = SessionLocal()
    try:
        # ---- 查询触发消息之前的 N 条（排除 @bot 消息） ----
        pre_rows = db.execute(
            text(
                "SELECT sender_name, message_type, content_preview, created_at "
                "FROM message_logs "
                "WHERE room_id = :room_id AND id < :trigger_id AND is_at_bot = 0 "
                "ORDER BY id DESC LIMIT :limit"
            ),
            {"room_id": room_id, "trigger_id": trigger_log_id, "limit": CLASSIFY_PRE_MSG_COUNT},
        ).mappings().all()
        pre_msgs = list(reversed(pre_rows))  # 恢复时间正序

        # ---- 查询触发消息之后 2.5 分钟内的所有消息 ----
        post_rows = db.execute(
            text(
                "SELECT sender_name, message_type, content_preview, created_at "
                "FROM message_logs "
                "WHERE room_id = :room_id AND id > :trigger_id "
                "AND created_at <= DATE_ADD(:trigger_at, INTERVAL :window SECOND) "
                "ORDER BY id ASC"
            ),
            {
                "room_id": room_id,
                "trigger_id": trigger_log_id,
                "trigger_at": trigger_created_at,
                "window": CLASSIFY_WINDOW_SECONDS,
            },
        ).mappings().all()

        # ---- 构建 context_messages ----
        context: list[dict[str, Any]] = []
        for r in pre_msgs:
            context.append({
                "type": "text",
                "content": f"[{r['sender_name'] or ''}] {r['content_preview'] or ''}",
            })
        context.append({"type": "text", "content": "===== 以下是客户发送的报货消息 ====="})
        for r in post_rows:
            context.append({
                "type": "text",
                "content": f"[{r['sender_name'] or ''}] {r['content_preview'] or ''}",
            })

        if not pre_msgs and not post_rows:
            # 没有上下文可判断，默认新下单
            db.execute(
                text(
                    "UPDATE downstream_order_reviews "
                    "SET order_intent = 'new', order_intent_reason = '无上下文消息，默认新下单' "
                    "WHERE id = :id"
                ),
                {"id": review_id},
            )
            db.commit()
            logger.info("[OrderClassify] review=%d 无上下文，默认 intent=new", review_id)
            return

        # ---- 调用分类 AI ----
        parser = AIOrderParser()
        result = await parser.classify_order(context, db=db)
        intent = result.get("intent", "new")
        reason = result.get("reason", "")
        logger.info("[OrderClassify] review=%d intent=%s confidence=%s reason=%s",
                    review_id, intent, result.get("confidence"), reason)

        # ---- 写入审核记录 ----
        db.execute(
            text(
                "UPDATE downstream_order_reviews "
                "SET order_intent = :intent, order_intent_reason = :reason "
                "WHERE id = :id"
            ),
            {"id": review_id, "intent": intent, "reason": (reason or "")[:500]},
        )
        db.commit()
    except Exception as exc:
        logger.warning("[OrderClassify] review=%d 分类异常: %s", review_id, exc)
        try:
            db.rollback()
        except Exception:
            pass
    finally:
        db.close()


def _build_validate_context(
    extracted: dict[str, Any],
    log_result: Optional[dict[str, Any]],
) -> list[dict[str, Any]]:
    """根据 _extract_callback_message 的结果构建 validate_order 所需的 context_messages。

    返回空列表表示没有可验证的内容。
    """
    msg_type = extracted.get("message_type") or "text"
    content_text = (extracted.get("content_text") or "").strip()
    attachment_base64 = extracted.get("attachment_base64") or ""
    attachment_name = extracted.get("attachment_name") or ""

    # 补充 content_text：如果 extracted 没有，从 log_result 取
    if not content_text and log_result:
        content_text = str(log_result.get("content_preview") or "").strip()

    msgs: list[dict[str, Any]] = []

    if msg_type == "image":
        if attachment_base64:
            mime = extracted.get("attachment_mime") or "image/png"
            msgs.append({"type": "image", "base64": attachment_base64, "mime": mime})
        elif content_text:
            # 图片无 base64 但有说明文字，用文字验证
            msgs.append({"type": "text", "content": content_text})
        # 图片既没 base64 也没文字 → 返回空，保守放行（由调用方兜底）
    elif msg_type == "file":
        if attachment_base64 and attachment_name.lower().endswith((".xlsx", ".xls")):
            from app.services.downstream_orders import _extract_excel_summary
            summary = _extract_excel_summary(attachment_base64)
            if summary:
                msgs.append({"type": "file", "file_name": attachment_name, "excel_summary": summary})
        elif content_text:
            msgs.append({"type": "text", "content": content_text})
    else:
        # 文字类消息
        if content_text:
            msgs.append({"type": "text", "content": content_text})

    return msgs


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

    # ===== 客户群专线：统一走通用审核链 create_review_from_callback =====
    review_result = None

    if not customer:
        logger.info("客户群专线跳过: customer 未找到 room=%s instance=%s", room_id, resolved_instance_id)
    elif sender_is_employee:
        logger.info("客户群专线跳过: 发送者是员工 sender=%s room=%s", log_sender_id, room_id)

    if customer and not sender_is_employee:
        try:
            # 标记 @bot 消息
            _is_at = False
            bot_wxid = effective_wxid or _safe_text(normalized_payload.get("wxid"))
            if (bot_wxid or resolved_instance_id) and is_at_bot(normalized_payload, bot_wxid, resolved_instance_id):
                _is_at = True
                _log_id = (log_result or {}).get("id")
                if _log_id:
                    try:
                        db.execute(text("UPDATE message_logs SET is_at_bot = 1 WHERE id = :id"), {"id": _log_id})
                        db.commit()
                    except Exception:
                        pass

            # 判断消息子类型
            is_image = log_msg_type in ("image", "img", "picture")
            is_excel = False
            if log_msg_type == "file":
                _msg_data = (normalized_payload.get("message") or {}).get("data") or normalized_payload.get("data") or {}
                if isinstance(_msg_data, str):
                    _msg_data = {}
                _file_name = str(
                    _msg_data.get("file_name") or _msg_data.get("filename")
                    or normalized_payload.get("file_name") or normalized_payload.get("filename")
                    or (log_result or {}).get("content_preview") or ""
                ).lower()
                is_excel = _file_name.endswith((".xlsx", ".xls"))

            # ---- 构建验证上下文 ----
            extracted = _extract_callback_message(normalized_payload, resolved_instance_id or None)
            ctx_msgs = _build_validate_context(extracted, log_result)

            # ---- 优先检查：是否有该发送人的挂起会话 ----
            pending_session = None
            try:
                pending_session = find_active_session(db, room_id, log_sender_id)
            except Exception as ps_exc:
                logger.debug("查找挂起会话异常: %s", ps_exc)

            if pending_session:
                logger.info("发现挂起会话 id=%d room=%s sender=%s, 进入补全流程",
                            pending_session["id"], room_id, log_sender_id)
                followup_result = await _handle_pending_session_followup(
                    db, pending_session, ctx_msgs,
                    room_id, log_sender_id, resolved_instance_id,
                    normalized_payload,
                )
                review_result = followup_result.get("review")
                # 无论补全是否成功，此消息已被挂起会话处理
                return {
                    "instanceId": resolved_instance_id,
                    "wxid": effective_wxid or _safe_text(normalized_payload.get("wxid")),
                    "received": True,
                    "log": log_result,
                    "review": review_result,
                    "shipping_scan_triggered": False,
                    "pending_session_handled": True,
                }

            # ---- 定期清理过期会话 ----
            try:
                cleanup_expired_sessions(db)
            except Exception:
                pass

            # ---- 报货验证：判断是否为报货信息 + 信息完整性 ----
            is_order = False
            is_complete = True
            missing_fields: list[str] = []
            validation_reason = ""
            if ctx_msgs:
                try:
                    parser = AIOrderParser()
                    validation = await parser.validate_order(ctx_msgs, db=db)
                    is_order = validation.get("is_order", False)
                    is_complete = validation.get("is_complete", True)
                    missing_fields = validation.get("missing_fields") or []
                    validation_reason = validation.get("reason", "")
                    logger.info("报货验证: room=%s is_order=%s is_complete=%s missing=%s reason=%s",
                                room_id, is_order, is_complete, missing_fields, validation_reason)
                except Exception as val_exc:
                    is_order = True
                    is_complete = True  # 验证异常时保守放行
                    logger.warning("报货验证异常，保守处理为完整报货: room=%s err=%s", room_id, val_exc)
            else:
                is_order = is_image or is_excel
                logger.debug("报货验证: 无可验证内容，保守判定 is_order=%s room=%s type=%s",
                             is_order, room_id, log_msg_type)

            # ---- 非报货消息：跳过 ----
            if not is_order:
                logger.info("客户群非报货消息，跳过: room=%s type=%s", room_id, log_msg_type)
                return {
                    "instanceId": resolved_instance_id,
                    "wxid": effective_wxid or _safe_text(normalized_payload.get("wxid")),
                    "received": True,
                    "log": log_result,
                    "review": None,
                    "shipping_scan_triggered": False,
                    "order_validated": False,
                }

            # ---- 是报货但信息不完整：挂起会话 ----
            if not is_complete and missing_fields:
                logger.info("报货信息不完整，创建挂起会话: room=%s sender=%s missing=%s",
                            room_id, log_sender_id, missing_fields)
                try:
                    create_pending_session(
                        db=db,
                        room_id=room_id,
                        sender_id=log_sender_id,
                        instance_id=resolved_instance_id,
                        customer_id=customer.get("id") if customer else None,
                        customer_name=customer.get("customer_name", "") if customer else "",
                        missing_fields=missing_fields,
                        context_messages=ctx_msgs,
                        original_payload=normalized_payload,
                        ai_reason=validation_reason,
                    )
                    # 通知客户缺少什么
                    if _is_after_startup():
                        asyncio.create_task(_reply_missing_fields(
                            room_id, log_sender_id, resolved_instance_id, missing_fields,
                        ))
                except Exception as ps_exc:
                    logger.warning("创建挂起会话失败: %s", ps_exc)
                return {
                    "instanceId": resolved_instance_id,
                    "wxid": effective_wxid or _safe_text(normalized_payload.get("wxid")),
                    "received": True,
                    "log": log_result,
                    "review": None,
                    "shipping_scan_triggered": False,
                    "order_incomplete": True,
                    "missing_fields": missing_fields,
                }

            # ---- 是完整报货消息：回复"收到" + 走审核链 ----
            if (_is_at or is_image or is_excel) and _is_after_startup():
                asyncio.create_task(_reply_received(room_id, log_sender_id, resolved_instance_id))

            review_result = await create_review_from_callback(db, normalized_payload, resolved_instance_id or None)
            logger.info("客户群审核: room=%s review=%s", room_id,
                        review_result.get("id") if isinstance(review_result, dict) and not review_result.get("skipped") else "skipped")
        except Exception as exc:
            logger.warning("客户群审核创建异常: %s", exc)
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
