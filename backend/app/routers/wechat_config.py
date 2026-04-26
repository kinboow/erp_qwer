import asyncio
import logging
from typing import Any, Optional

import httpx
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.models import User
from app.services.wechat_ws_service import wechat_ws_service

router = APIRouter(tags=["企微全局配置"])


class WechatConfigDto(BaseModel):
    host: Optional[str] = ""
    port: Optional[str] = ""
    api_key: Optional[str] = ""
    selected_wxid: Optional[str] = ""
    ws_path: Optional[str] = "/ws/wechat/messages"
    http_path: Optional[str] = "/api/wechat/callback/http"
    callback_timeout: Optional[int] = 5


def json_response(code=200, message="success", data=None):
    resp = {"code": code, "message": message}
    if data is not None:
        resp["data"] = data
    return resp


def ensure_wechat_config_table(db: Session):
    db.execute(text(
        "CREATE TABLE IF NOT EXISTS wechat_config ("
        "id INT UNSIGNED NOT NULL PRIMARY KEY, "
        "host VARCHAR(255) NOT NULL DEFAULT '', "
        "port VARCHAR(50) NOT NULL DEFAULT '', "
        "api_key VARCHAR(255) NOT NULL DEFAULT '', "
        "selected_wxid VARCHAR(100) NOT NULL DEFAULT '', "
        "ws_path VARCHAR(255) NOT NULL DEFAULT '/ws/wechat/messages', "
        "http_path VARCHAR(255) NOT NULL DEFAULT '/api/wechat/callback/http', "
        "callback_timeout INT NOT NULL DEFAULT 5"
        ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4"
    ))
    db.execute(text(
        "INSERT IGNORE INTO wechat_config ("
        "id, host, port, api_key, selected_wxid, ws_path, http_path, callback_timeout"
        ") VALUES ("
        "1, '', '', '', '', '/ws/wechat/messages', '/api/wechat/callback/http', 5"
        ")"
    ))
    db.commit()


@router.get("/config", summary="获取企微全局配置")
async def get_wechat_config(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    ensure_wechat_config_table(db)
    row = db.execute(text("SELECT * FROM wechat_config WHERE id = 1")).mappings().first()
    if not row:
        return json_response(data={
            "host": "", "port": "", "api_key": "", "selected_wxid": "",
            "ws_path": "/ws/wechat/messages", "http_path": "/api/wechat/callback/http",
            "callback_timeout": 5
        })
    return json_response(data=dict(row))


@router.put("/config", summary="保存企微全局配置")
async def save_wechat_config(
    payload: WechatConfigDto,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    try:
        ensure_wechat_config_table(db)
        db.execute(text(
            "UPDATE wechat_config SET "
            "host = :host, port = :port, api_key = :api_key, "
            "selected_wxid = :selected_wxid, "
            "ws_path = :ws_path, http_path = :http_path, callback_timeout = :callback_timeout "
            "WHERE id = 1"
        ), {
            "host": payload.host or "",
            "port": payload.port or "",
            "api_key": payload.api_key or "",
            "selected_wxid": payload.selected_wxid or "",
            "ws_path": payload.ws_path or "/ws/wechat/messages",
            "http_path": payload.http_path or "/api/wechat/callback/http",
            "callback_timeout": payload.callback_timeout or 5,
        })
        db.commit()

        # 后台恢复 WebSocket 与刷新企微健康状态（不阻塞保存响应）
        try:
            from app.services.wechat_health import refresh_wechat_health_status
            asyncio.create_task(wechat_ws_service.auto_connect_from_saved_config())
            asyncio.create_task(refresh_wechat_health_status())
        except Exception:
            pass

        return json_response(message="配置已保存")
    except Exception as exc:
        try:
            db.rollback()
        except Exception:
            pass
        return json_response(code=500, message=f"保存配置失败: {exc}")


# ---------------------------------------------------------------------------
# 群聊管理（全量列表 / 状态 / 内部群 / 成员）
# ---------------------------------------------------------------------------
_room_logger = logging.getLogger(__name__)


def _build_api_base_url(host: str, port: str) -> str:
    host = (host or "").strip()
    port = (port or "").strip()
    if not host:
        return ""
    base = host if host.startswith(("http://", "https://")) else f"http://{host}"
    if port and port not in ("80", "443"):
        base = f"{base}:{port}"
    return base.rstrip("/")


def _get_wechat_cfg(db: Session):
    """返回 (api_base, wxid, headers) 或抛异常"""
    ensure_wechat_config_table(db)
    cfg = db.execute(text(
        "SELECT host, port, api_key, selected_wxid FROM wechat_config WHERE id = 1"
    )).mappings().first()
    if not cfg or not cfg.get("host"):
        raise ValueError("请先配置企微 API 连接")
    api_base = _build_api_base_url(cfg["host"], cfg["port"])
    wxid = cfg.get("selected_wxid") or ""
    if not api_base or not wxid:
        raise ValueError("缺少 API 地址或未选择实例")
    headers: dict[str, str] = {"Content-Type": "application/json"}
    if cfg.get("api_key"):
        headers["X-API-Key"] = cfg["api_key"]
    return api_base, wxid, headers


def _ensure_internal_rooms_table(db: Session):
    from app.services.downstream_support import ensure_downstream_support_tables
    ensure_downstream_support_tables(db)


# ---- 获取全部群聊 (从企微 API) ----

@router.get("/proxy/rooms", summary="代理获取全部群聊列表")
async def proxy_get_rooms(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """分页拉取企微 API 的全部群聊，合并返回"""
    try:
        api_base, wxid, headers = _get_wechat_cfg(db)
    except ValueError as e:
        return json_response(code=400, message=str(e))

    all_rooms: list[dict] = []
    page = 1
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            while True:
                resp = await client.post(
                    f"{api_base}/api/{wxid}/rooms/get",
                    json={"page_num": page, "page_size": 200},
                    headers=headers,
                )
                resp.raise_for_status()
                result = resp.json()
                inner = (result.get("data") or {}) if isinstance(result, dict) else {}
                room_list = []
                if isinstance(inner, dict):
                    room_list = inner.get("room_list") or inner.get("rooms") or inner.get("list") or []
                elif isinstance(inner, list):
                    room_list = inner
                all_rooms.extend(room_list)
                total = inner.get("total", 0) if isinstance(inner, dict) else 0
                if not room_list or len(all_rooms) >= total:
                    break
                page += 1
                if page > 50:
                    break
        return json_response(data=all_rooms)
    except ValueError as e:
        return json_response(code=400, message=str(e))
    except Exception as exc:
        return json_response(code=502, message=f"获取群聊列表失败: {exc}")


# ---- 全部群聊 + 状态合并 ----

@router.get("/rooms/all-status", summary="获取全部群聊及关联状态")
async def get_rooms_all_status(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """拉取企微群聊，合并 DB 中客户关联和内部群状态"""
    # 1) 从企微 API 获取群聊
    try:
        api_base, wxid, headers = _get_wechat_cfg(db)
    except ValueError as e:
        return json_response(code=400, message=str(e))

    all_rooms: list[dict] = []
    page = 1
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            while True:
                resp = await client.post(
                    f"{api_base}/api/{wxid}/rooms/get",
                    json={"page_num": page, "page_size": 200},
                    headers=headers,
                )
                resp.raise_for_status()
                result = resp.json()
                inner = (result.get("data") or {}) if isinstance(result, dict) else {}
                room_list = []
                if isinstance(inner, dict):
                    room_list = inner.get("room_list") or inner.get("rooms") or inner.get("list") or []
                elif isinstance(inner, list):
                    room_list = inner
                all_rooms.extend(room_list)
                total = inner.get("total", 0) if isinstance(inner, dict) else 0
                if not room_list or len(all_rooms) >= total:
                    break
                page += 1
                if page > 50:
                    break
    except Exception as exc:
        return json_response(code=502, message=f"获取群聊列表失败: {exc}")

    # 2) 从 DB 查客户群关联
    customer_map: dict[str, dict] = {}
    try:
        rows = db.execute(text(
            "SELECT r.room_id, r.customer_id, c.customer_name, c.contact_person, c.erp_customer_id "
            "FROM downstream_customer_wechat_rooms r "
            "INNER JOIN downstream_customers c ON c.id = r.customer_id "
            "WHERE c.deleted_at IS NULL AND c.status = 1"
        )).mappings().all()
        for r in rows:
            customer_map[r["room_id"]] = {
                "customer_id": r["customer_id"],
                "customer_name": r["customer_name"],
                "contact_person": r["contact_person"],
                "erp_customer_id": r["erp_customer_id"],
            }
    except Exception:
        pass

    # 3) 从 DB 查内部群
    internal_map: dict[str, dict] = {}
    try:
        _ensure_internal_rooms_table(db)
        irows = db.execute(text(
            "SELECT room_id, room_type, remark FROM internal_wechat_rooms"
        )).mappings().all()
        for r in irows:
            internal_map[r["room_id"]] = {
                "room_type": r["room_type"],
                "remark": r["remark"],
            }
    except Exception:
        pass

    # 4) 合并
    merged = []
    for room in all_rooms:
        rid = room.get("conversation_id") or room.get("room_id") or ""
        # 去掉 R: 前缀用于 DB 匹配
        rid_clean = rid[2:] if rid.startswith("R:") else rid
        cust = customer_map.get(rid_clean) or customer_map.get(rid)
        intern = internal_map.get(rid_clean) or internal_map.get(rid)
        merged.append({
            "conversation_id": rid,
            "room_id": rid_clean,
            "room_name": room.get("nickname") or room.get("room_name") or room.get("name") or "",
            "member_count": room.get("member_count") or room.get("total") or 0,
            "owner": room.get("owner") or "",
            "is_customer": cust is not None,
            "customer": cust,
            "is_internal": intern is not None,
            "internal": intern,
        })

    return json_response(data=merged)


# ---- 设置 / 取消内部群 ----

class SetInternalReq(BaseModel):
    room_id: str
    room_name: Optional[str] = ""
    room_type: Optional[str] = "shipping"
    remark: Optional[str] = ""


@router.post("/rooms/set-internal", summary="设置为内部群聊")
async def set_internal_room(
    data: SetInternalReq,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _ensure_internal_rooms_table(db)
    rid = data.room_id
    # 检查是否已关联客户
    cust = db.execute(text(
        "SELECT r.room_id FROM downstream_customer_wechat_rooms r "
        "INNER JOIN downstream_customers c ON c.id = r.customer_id "
        "WHERE r.room_id = :rid AND c.deleted_at IS NULL AND c.status = 1 LIMIT 1"
    ), {"rid": rid}).mappings().first()
    if cust:
        return json_response(code=400, message="该群聊已关联客户，不能设置为内部群")
    try:
        db.execute(text(
            "INSERT INTO internal_wechat_rooms (room_id, room_name, room_type, remark) "
            "VALUES (:room_id, :room_name, :room_type, :remark) "
            "ON DUPLICATE KEY UPDATE room_name = :room_name, room_type = :room_type, remark = :remark"
        ), {
            "room_id": rid,
            "room_name": data.room_name or "",
            "room_type": data.room_type or "shipping",
            "remark": data.remark or "",
        })
        db.commit()
        return json_response(message="已设置为内部群")
    except Exception as exc:
        db.rollback()
        return json_response(code=500, message=f"设置内部群失败: {exc}")


class UnsetInternalReq(BaseModel):
    room_id: str


@router.post("/rooms/unset-internal", summary="取消内部群聊")
async def unset_internal_room(
    data: UnsetInternalReq,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _ensure_internal_rooms_table(db)
    try:
        db.execute(text("DELETE FROM internal_wechat_rooms WHERE room_id = :rid"), {"rid": data.room_id})
        db.commit()
        return json_response(message="已取消内部群")
    except Exception as exc:
        db.rollback()
        return json_response(code=500, message=f"取消内部群失败: {exc}")


# ---- 代理获取群成员 ----

class RoomMembersReq(BaseModel):
    room_id: str


@router.post("/proxy/room-members", summary="代理获取群成员列表")
async def proxy_room_members(
    data: RoomMembersReq,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        api_base, wxid, headers = _get_wechat_cfg(db)
    except ValueError as e:
        return json_response(code=400, message=str(e))

    conversation_id = data.room_id if data.room_id.startswith("R:") else f"R:{data.room_id}"
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                f"{api_base}/api/{wxid}/rooms/members",
                json={"conversation_id": conversation_id, "page_num": 1, "page_size": 500},
                headers=headers,
            )
            resp.raise_for_status()
            result = resp.json()
        members = []
        if isinstance(result, dict):
            inner = result.get("data") or {}
            if isinstance(inner, dict):
                members = inner.get("member_list") or inner.get("members") or []
            elif isinstance(inner, list):
                members = inner
        return json_response(data=members)
    except Exception as exc:
        return json_response(code=502, message=f"获取群成员失败: {exc}")
