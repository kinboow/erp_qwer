"""
审核订单事件广播 — 用于 SSE 推送新审核单通知到前端 + 通知群
"""

import asyncio
import logging
from typing import Any

from sqlalchemy import text

_logger = logging.getLogger(__name__)

# 所有活跃的 SSE 订阅者队列
_subscribers: list[asyncio.Queue] = []


def notify_review_change(event_type: str = "new_review", data: dict[str, Any] | None = None):
    """广播审核单变动事件给所有 SSE 订阅者，同时推送通知群"""
    payload = {"event": event_type, **(data or {})}
    stale = []
    for q in _subscribers:
        try:
            q.put_nowait(payload)
        except asyncio.QueueFull:
            stale.append(q)
    for q in stale:
        _subscribers.remove(q)
    if _subscribers:
        _logger.debug("[SSE] 广播 %s 给 %d 个订阅者", event_type, len(_subscribers))

    # 新审核单 → 通知群推送
    if event_type == "new_review" and data and data.get("review_id"):
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(_push_new_review_to_groups(data["review_id"]))
        except RuntimeError:
            pass


async def _push_new_review_to_groups(review_id: int) -> None:
    """查询审核单简要信息并推送通知群"""
    try:
        from app.database import SessionLocal
        from app.services.notify_group import send_to_notification_groups
        db = SessionLocal()
        try:
            row = db.execute(
                text(
                    "SELECT id, review_uid, review_type, customer_name, content_text, sender_name "
                    "FROM downstream_order_reviews WHERE id = :id"
                ),
                {"id": review_id},
            ).mappings().first()
        finally:
            db.close()
        if not row:
            return
        rtype = row.get("review_type") or "normal"
        emoji = "📝" if rtype == "modify" else "📋"
        type_label = "待修改" if rtype == "modify" else "新报货"
        uid = row.get("review_uid") or f"#{review_id}"
        cname = row.get("customer_name") or "未知客户"
        sender = row.get("sender_name") or ""
        summary = (row.get("content_text") or "")[:120]
        msg = f"{emoji} {type_label}审核单 {uid}\n客户：{cname}"
        if sender:
            msg += f"\n发送人：{sender}"
        if summary:
            msg += f"\n内容：{summary}"
        await send_to_notification_groups(None, msg)
    except Exception as exc:
        _logger.warning("[通知群] 推送新审核单失败: %s", exc)


async def subscribe():
    """创建一个新的 SSE 订阅，返回异步生成器"""
    q: asyncio.Queue = asyncio.Queue(maxsize=50)
    _subscribers.append(q)
    try:
        while True:
            payload = await q.get()
            yield payload
    finally:
        if q in _subscribers:
            _subscribers.remove(q)
