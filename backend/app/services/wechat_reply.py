"""
企微群消息回复封装
调用 /api/{wxid}/send/text 和 /api/{wxid}/send/room_at
"""

from __future__ import annotations

import logging
from typing import Any, Optional

import httpx
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models import WechatInstance

logger = logging.getLogger(__name__)


def _build_wechat_headers(api_key: str) -> dict[str, str]:
    headers: dict[str, str] = {}
    if api_key:
        headers["X-API-Key"] = api_key
    return headers


def _resolve_runtime(db: Session, instance_id: Optional[int] = None) -> dict[str, Any]:
    """获取企微运行时配置（api_base_url, wxid, api_key）"""
    if instance_id:
        inst = db.query(WechatInstance).filter(WechatInstance.id == instance_id).first()
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
        if host:
            base = host if host.startswith(("http://", "https://")) else f"http://{host}"
            if port and port not in ("80", "443"):
                base = f"{base}:{port}"
        else:
            base = ""
        return {
            "api_base_url": base.rstrip("/"),
            "api_key": row.get("api_key") or "",
            "wxid": row.get("selected_wxid") or "",
        }
    return {"api_base_url": "", "api_key": "", "wxid": ""}


async def send_room_at(
    db: Session,
    room_id: str,
    content: str,
    at_list: list[str] | None = None,
    instance_id: Optional[int] = None,
    source: str | int | None = None,
) -> dict[str, Any]:
    """发送群@消息。room_id 不含 R: 前缀时自动补全。
    source: 引用消息的 server_id，传入后消息将引用该条原始消息。
    """
    runtime = _resolve_runtime(db, instance_id)
    if not runtime.get("api_base_url") or not runtime.get("wxid"):
        logger.warning("缺少企微运行时配置，无法发送群回复")
        return {"ok": False, "error": "missing_runtime_config"}

    conversation_id = room_id if room_id.startswith("R:") else f"R:{room_id}"
    api_base = runtime["api_base_url"]
    wxid = runtime["wxid"]
    headers = _build_wechat_headers(runtime.get("api_key") or "")

    if at_list:
        url = f"{api_base}/api/{wxid}/send/room_at"
        body: dict[str, Any] = {"conversation_id": conversation_id, "content": content, "at_list": at_list}
    else:
        url = f"{api_base}/api/{wxid}/send/text"
        body = {"conversation_id": conversation_id, "content": content}

    if source:
        body["source"] = str(source)

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(url, json=body, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            return {"ok": True, "data": data}
    except Exception as exc:
        logger.error("发送群回复失败: %s", exc)
        return {"ok": False, "error": str(exc)}
