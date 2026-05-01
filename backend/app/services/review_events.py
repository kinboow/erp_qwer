"""
审核订单事件广播 — 用于 SSE 推送新审核单通知到前端
"""

import asyncio
import logging
from typing import Any

_logger = logging.getLogger(__name__)

# 所有活跃的 SSE 订阅者队列
_subscribers: list[asyncio.Queue] = []


def notify_review_change(event_type: str = "new_review", data: dict[str, Any] | None = None):
    """广播审核单变动事件给所有 SSE 订阅者"""
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
