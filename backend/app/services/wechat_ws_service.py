import asyncio
import contextlib
import json
import logging
from typing import Dict, Optional
from urllib.parse import quote

import websockets
from sqlalchemy import text

from app.database import SessionLocal
from app.services.message_logs import record_message_log_background

logger = logging.getLogger(__name__)


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

    async def disconnect_all(self, keep_instance_id: Optional[str] = None):
        target_keep = str(keep_instance_id or "").strip()
        instance_ids = [instance_id for instance_id in list(self.connections.keys()) if not target_keep or instance_id != target_keep]
        for instance_id in instance_ids:
            await self.disconnect(instance_id)

    async def auto_connect_from_saved_config(self):
        db = SessionLocal()
        try:
            config_row = db.execute(
                text("SELECT host, port, api_key, selected_wxid, ws_path FROM wechat_config WHERE id = 1")
            ).mappings().first()
            if not config_row:
                await self.disconnect_all()
                return None

            selected_wxid = str(config_row.get("selected_wxid") or "").strip()
            if not selected_wxid:
                await self.disconnect_all()
                return None

            host = str(config_row.get("host") or "").strip()
            port = str(config_row.get("port") or "").strip()
            if not host:
                await self.disconnect_all()
                return None

            if host.startswith(("http://", "https://", "ws://", "wss://")):
                api_base_url = host.rstrip("/") if not port else f"{host.rstrip('/')}:{port}"
            else:
                api_base_url = f"http://{host}"
                if port:
                    api_base_url = f"{api_base_url}:{port}"

            ws_url = self._build_ws_url(api_base_url, str(config_row.get("ws_path") or ""), selected_wxid)
            if not ws_url:
                await self.disconnect_all()
                return None

            await self.disconnect_all(keep_instance_id=selected_wxid)
            return await self.connect(selected_wxid, ws_url)
        except Exception:
            return None
        finally:
            db.close()

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
                        asyncio.create_task(self._ingest_ws_message(normalized, instance_id))
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                state = self.connections.get(instance_id)
                if not state or state.get("manual"):
                    return
                state["readyState"] = "closed"
                state["lastError"] = str(exc)
                await asyncio.sleep(5)

    @staticmethod
    async def _ingest_ws_message(normalized: any, instance_id: str):
        """通过完整的 ingest_runtime_message 流程处理 WS 消息（含 @检测、AI 解析等）"""
        try:
            from app.services.wechat_runtime_compat import ingest_runtime_message
            from app.services import ws_notify
            db = SessionLocal()
            try:
                await ingest_runtime_message(
                    db, normalized,
                    source="websocket",
                    instance_id=instance_id,
                )
                await ws_notify.broadcast("new_message_log")
            finally:
                db.close()
        except Exception as exc:
            logger.warning("WS 消息处理异常: %s", exc)

    def _serialize(self, state: dict):
        return {
            "instanceId": state.get("instanceId"),
            "url": state.get("url"),
            "readyState": state.get("readyState", "unknown"),
            "lastMessage": state.get("lastMessage"),
            "lastError": state.get("lastError"),
        }

    @staticmethod
    def _build_ws_url(api_base_url: str, ws_path: str, instance_id: str) -> str:
        normalized_base = str(api_base_url or "").strip().rstrip("/")
        normalized_instance_id = str(instance_id or "").strip()
        if not normalized_base or not normalized_instance_id:
            return ""

        if normalized_base.startswith("https://"):
            normalized_base = f"wss://{normalized_base[8:]}"
        elif normalized_base.startswith("http://"):
            normalized_base = f"ws://{normalized_base[7:]}"
        elif not normalized_base.startswith(("ws://", "wss://")):
            normalized_base = f"ws://{normalized_base}"

        normalized_path = str(ws_path or "").strip() or "/ws/wechat/messages"
        if not normalized_path.startswith("/"):
            normalized_path = f"/{normalized_path}"
        return f"{normalized_base}{normalized_path}?instanceId={quote(normalized_instance_id)}"

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
