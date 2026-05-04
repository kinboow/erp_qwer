"""
轻量级 WebSocket 广播：通知前端刷新数据
"""

import asyncio
import json
import logging
from typing import Any, Set

from fastapi import WebSocket

logger = logging.getLogger(__name__)

_clients: Set[WebSocket] = set()
_main_loop: asyncio.AbstractEventLoop | None = None


def set_main_loop(loop: asyncio.AbstractEventLoop):
    """应用启动时调用，保存主事件循环引用供后台线程使用"""
    global _main_loop
    _main_loop = loop


async def register(ws: WebSocket):
    await ws.accept()
    _clients.add(ws)


def unregister(ws: WebSocket):
    _clients.discard(ws)


async def broadcast(event: str, data: Any = None):
    """向所有已连接的前端客户端广播事件"""
    if not _clients:
        return
    message = json.dumps({"event": event, "data": data}, ensure_ascii=False, default=str)
    stale: list[WebSocket] = []
    for ws in _clients.copy():
        try:
            await ws.send_text(message)
        except Exception:
            stale.append(ws)
    for ws in stale:
        _clients.discard(ws)


def broadcast_sync(event: str, data: Any = None):
    """在同步上下文中触发广播（fire-and-forget），支持从后台线程调用"""
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(broadcast(event, data))
    except RuntimeError:
        # 不在 asyncio 线程中，使用保存的主事件循环
        if _main_loop and _main_loop.is_running():
            _main_loop.call_soon_threadsafe(_main_loop.create_task, broadcast(event, data))
