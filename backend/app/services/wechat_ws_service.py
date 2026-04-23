import asyncio
import contextlib
import json
from typing import Dict, Optional

import websockets

from app.services.message_logs import record_message_log_background


class WechatWsService:
    def __init__(self):
        self.connections: Dict[str, dict] = {}

    async def connect(self, instance_id: str, url: str):
        if not instance_id:
            raise ValueError("instanceId 不能为空")
        if not url:
            raise ValueError("WebSocket 地址不能为空")

        await self.disconnect(instance_id)

        state = {
            "instanceId": instance_id,
            "url": url,
            "readyState": "connecting",
            "manual": False,
            "task": None,
        }
        task = asyncio.create_task(self._run_connection(instance_id, url))
        state["task"] = task
        self.connections[instance_id] = state
        return {"instanceId": instance_id, "url": url, "status": "connecting"}

    async def disconnect(self, instance_id: str):
        state = self.connections.get(instance_id)
        if not state:
            return False
        state["manual"] = True
        task = state.get("task")
        if task:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
        self.connections.pop(instance_id, None)
        return True

    def get_status(self, instance_id: Optional[str] = None):
        if instance_id:
            state = self.connections.get(instance_id)
            if not state:
                return None
            return self._serialize(state)
        return [self._serialize(item) for item in self.connections.values()]

    async def _run_connection(self, instance_id: str, url: str):
        while True:
            state = self.connections.get(instance_id)
            if not state or state.get("manual"):
                return
            try:
                state["readyState"] = "connecting"
                async with websockets.connect(url) as websocket:
                    state["readyState"] = "open"
                    async for message in websocket:
                        normalized = self._normalize_message(message)
                        state["lastMessage"] = normalized
                        record_message_log_background(normalized, source="websocket", instance_id=instance_id)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                state = self.connections.get(instance_id)
                if not state or state.get("manual"):
                    return
                state["readyState"] = "closed"
                state["lastError"] = str(exc)
                await asyncio.sleep(5)

    def _serialize(self, state: dict):
        return {
            "instanceId": state.get("instanceId"),
            "url": state.get("url"),
            "readyState": state.get("readyState", "unknown"),
            "lastMessage": state.get("lastMessage"),
            "lastError": state.get("lastError"),
        }

    @staticmethod
    def _normalize_message(message):
        if isinstance(message, bytes):
            try:
                return message.decode("utf-8")
            except Exception:
                return message.hex()
        if isinstance(message, str):
            try:
                return json.loads(message)
            except Exception:
                return message
        return str(message)


wechat_ws_service = WechatWsService()
