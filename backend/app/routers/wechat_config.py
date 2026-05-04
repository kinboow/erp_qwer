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


_wechat_config_ensured = False


def ensure_wechat_config_table(db: Session):
    global _wechat_config_ensured
    if _wechat_config_ensured:
        return
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
    _wechat_config_ensured = True


@router.get("/config", summary="获取企微全局配置")
def get_wechat_config(
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
def save_wechat_config(
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


_rooms_table_ensured = False


def _ensure_internal_rooms_table(db: Session):
    global _rooms_table_ensured
    if _rooms_table_ensured:
        return
    from app.services.downstream_support import ensure_downstream_support_tables
    ensure_downstream_support_tables(db)
    _rooms_table_ensured = True


async def sync_room_names_to_customers(db: Session) -> int:
    """从企微 API 拉取最新群列表，更新 downstream_customer_wechat_rooms 中的 room_name。
    返回更新的记录数。可从任意需要刷新群名的地方调用。"""
    try:
        api_base, wxid, headers = _get_wechat_cfg(db)
    except (ValueError, Exception):
        return 0

    # 1) 拉取所有群聊
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
    except Exception:
        return 0

    # 2) 构建 room_id -> room_name 映射
    name_map: dict[str, str] = {}
    for room in all_rooms:
        rid = room.get("conversation_id") or room.get("room_id") or ""
        rid_clean = rid[2:] if rid.startswith("R:") else rid
        room_name = room.get("nickname") or room.get("room_name") or room.get("name") or ""
        if rid_clean and room_name:
            name_map[rid_clean] = room_name

    # 3) 批量更新
    updated = 0
    try:
        for room_id, room_name in name_map.items():
            r = db.execute(
                text(
                    "UPDATE downstream_customer_wechat_rooms "
                    "SET room_name = :room_name WHERE room_id = :room_id AND room_name != :room_name"
                ),
                {"room_id": room_id, "room_name": room_name},
            )
            updated += r.rowcount
        if updated:
            db.commit()
    except Exception:
        db.rollback()
    return updated


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
    api_ok = True
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
        api_ok = False
        logging.getLogger(__name__).warning("企微 API 拉取群聊失败，回退到数据库: %s", exc)
        # 回退：从 wechat_room_listeners 读取已同步的群聊
        try:
            from app.models import WechatInstance
            inst = db.query(WechatInstance).filter(WechatInstance.wxid == wxid).first()
            if inst:
                rows = db.execute(text(
                    "SELECT room_id, room_name FROM wechat_room_listeners WHERE instance_id = :iid"
                ), {"iid": inst.id}).mappings().all()
                all_rooms = [
                    {"conversation_id": r["room_id"], "room_id": r["room_id"],
                     "nickname": r["room_name"] or "", "member_count": 0}
                    for r in rows
                ]
        except Exception:
            pass

    # 2) 从 DB 查所有已分类群聊（统一表）
    _ensure_internal_rooms_table(db)
    room_db_map: dict[str, dict] = {}
    try:
        rows = db.execute(text(
            "SELECT r.room_id, r.room_type, r.remark, r.customer_id, "
            "c.customer_name, c.contact_person, c.erp_customer_id "
            "FROM downstream_customer_wechat_rooms r "
            "LEFT JOIN downstream_customers c ON c.id = r.customer_id "
            "AND c.deleted_at IS NULL AND c.status = 1"
        )).mappings().all()
        for r in rows:
            entry = {
                "room_type": r["room_type"] or "",
                "remark": r["remark"] or "",
                "customer_id": r["customer_id"],
            }
            if r["customer_id"] and r["customer_name"]:
                entry["customer"] = {
                    "customer_id": r["customer_id"],
                    "customer_name": r["customer_name"],
                    "contact_person": r["contact_person"],
                    "erp_customer_id": r["erp_customer_id"],
                }
            raw_rid = r["room_id"]
            clean_rid = raw_rid[2:] if raw_rid.startswith("R:") else raw_rid
            room_db_map[raw_rid] = entry
            if clean_rid != raw_rid:
                room_db_map[clean_rid] = entry
    except Exception as exc:
        logging.getLogger(__name__).warning("查询群类型设置失败: %s", exc)

    # 3) 合并
    merged = []
    name_map: dict[str, str] = {}
    for room in all_rooms:
        rid = room.get("conversation_id") or room.get("room_id") or ""
        rid_clean = rid[2:] if rid.startswith("R:") else rid
        db_info = room_db_map.get(rid_clean) or room_db_map.get(rid)
        room_name = room.get("nickname") or room.get("room_name") or room.get("name") or ""

        room_type = (db_info.get("room_type") or "") if db_info else ""
        is_customer = room_type == "customer"
        is_internal = room_type in ("shipping", "notification")
        customer = db_info.get("customer") if db_info else None

        merged.append({
            "conversation_id": rid,
            "room_id": rid_clean,
            "room_name": room_name,
            "member_count": room.get("member_count") or room.get("total") or 0,
            "owner": room.get("owner") or "",
            "type": room_type,
            "is_customer": is_customer,
            "customer": customer,
            "is_internal": is_internal,
            "internal": {"room_type": room_type, "remark": db_info.get("remark", "")} if is_internal else None,
        })
        if rid_clean and room_name:
            name_map[rid_clean] = room_name

    # 5) 批量更新群聊的 room_name（同时尝试有/无 R: 前缀）
    try:
        for room_id, room_name in name_map.items():
            db.execute(
                text(
                    "UPDATE downstream_customer_wechat_rooms "
                    "SET room_name = :room_name "
                    "WHERE room_id IN (:rid1, :rid2) AND room_name != :room_name"
                ),
                {"rid1": room_id, "rid2": f"R:{room_id}", "room_name": room_name},
            )
        db.commit()
    except Exception:
        db.rollback()

    return json_response(data=merged)


@router.get("/rooms/synced", summary="获取已同步到数据库的群聊列表")
async def get_synced_rooms(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """从数据库 wechat_room_listeners 获取已同步的群聊，不调用外部 API，速度快且可靠"""
    cfg = db.execute(text(
        "SELECT selected_wxid FROM wechat_config WHERE id = 1"
    )).mappings().first() or {}
    wxid = (cfg.get("selected_wxid") or "").strip()
    from app.models import WechatInstance
    rows = []
    if wxid:
        inst = db.query(WechatInstance).filter(WechatInstance.wxid == wxid).first()
        if inst:
            rows = db.execute(text(
                "SELECT room_id, room_name FROM wechat_room_listeners "
                "WHERE instance_id = :iid ORDER BY room_name ASC"
            ), {"iid": inst.id}).mappings().all()
    if not rows:
        rows = db.execute(text(
            "SELECT room_id, MAX(COALESCE(room_name, '')) AS room_name "
            "FROM wechat_room_listeners "
            "GROUP BY room_id "
            "ORDER BY room_name ASC, room_id ASC"
        )).mappings().all()
    if not rows:
        all_status = await get_rooms_all_status(db=db, current_user=current_user)
        data = all_status.get("data") or []
        if data:
            return json_response(data=[
                {
                    "room_id": (item.get("room_id") or item.get("conversation_id") or "").replace("R:", "", 1),
                    "room_name": item.get("room_name") or "未命名群聊"
                }
                for item in data
                if item.get("room_id") or item.get("conversation_id")
            ])
    return json_response(data=[
        {"room_id": r["room_id"], "room_name": r["room_name"] or "未命名群聊"}
        for r in rows if r.get("room_id")
    ])


# ---- 设置 / 取消内部群 ----

class SetInternalReq(BaseModel):
    room_id: str
    room_name: Optional[str] = ""
    room_type: Optional[str] = "shipping"
    remark: Optional[str] = ""


@router.post("/rooms/set-internal", summary="设置为内部群聊")
def set_internal_room(
    data: SetInternalReq,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _ensure_internal_rooms_table(db)
    raw_rid = data.room_id
    rid = raw_rid[2:] if raw_rid.startswith("R:") else raw_rid
    # 检查是否已关联客户（同时检查有/无 R: 前缀）
    cust = db.execute(text(
        "SELECT r.room_id FROM downstream_customer_wechat_rooms r "
        "WHERE r.room_id IN (:rid1, :rid2) AND r.room_type = 'customer' AND r.customer_id IS NOT NULL LIMIT 1"
    ), {"rid1": rid, "rid2": f"R:{rid}"}).mappings().first()
    if cust:
        return json_response(code=400, message="该群聊已关联客户，不能设置为内部群")
    try:
        # 先删除该 room_id 所有非客户类型的旧记录（含 R: 前缀和无前缀）
        db.execute(text(
            "DELETE FROM downstream_customer_wechat_rooms "
            "WHERE room_id IN (:rid1, :rid2) AND room_type != 'customer'"
        ), {"rid1": rid, "rid2": f"R:{rid}"})
        db.execute(text(
            "INSERT INTO downstream_customer_wechat_rooms (room_id, room_name, room_type, remark, customer_id) "
            "VALUES (:room_id, :room_name, :room_type, :remark, NULL)"
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
def unset_internal_room(
    data: UnsetInternalReq,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _ensure_internal_rooms_table(db)
    try:
        rid_raw = data.room_id
        rid_clean = rid_raw[2:] if rid_raw.startswith("R:") else rid_raw
        db.execute(text(
            "DELETE FROM downstream_customer_wechat_rooms "
            "WHERE room_id IN (:rid1, :rid2) AND room_type != 'customer'"
        ), {"rid1": rid_clean, "rid2": f"R:{rid_clean}"})
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


# ---------------------------------------------------------------------------
# 员工企微账号管理（排除监听）
# ---------------------------------------------------------------------------

_DDL_EMPLOYEE_ACCOUNTS = """
CREATE TABLE IF NOT EXISTS wechat_employee_accounts (
    id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    wxid VARCHAR(100) NOT NULL,
    nickname VARCHAR(200) DEFAULT '',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uk_wxid (wxid)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
"""


def _ensure_employee_accounts_table(db: Session):
    db.execute(text(_DDL_EMPLOYEE_ACCOUNTS))
    db.commit()


@router.get("/customer-room-members", summary="获取所有客户群去重成员列表")
async def get_customer_room_members(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """遍历所有客户群，拉取群成员并去重返回"""
    try:
        api_base, wxid, headers = _get_wechat_cfg(db)
    except ValueError as e:
        return json_response(code=400, message=str(e))

    # 查出所有客户群 room_id
    room_rows = db.execute(text(
        "SELECT DISTINCT r.room_id, r.room_name "
        "FROM downstream_customer_wechat_rooms r "
        "INNER JOIN downstream_customers c ON c.id = r.customer_id "
        "WHERE c.deleted_at IS NULL AND c.status = 1"
    )).mappings().all()
    if not room_rows:
        return json_response(data=[])

    # 并发拉取各群成员
    seen: dict[str, dict] = {}
    async with httpx.AsyncClient(timeout=15.0) as client:
        for row in room_rows:
            rid = row["room_id"]
            conversation_id = rid if rid.startswith("R:") else f"R:{rid}"
            try:
                resp = await client.post(
                    f"{api_base}/api/{wxid}/rooms/members",
                    json={"conversation_id": conversation_id, "page_num": 1, "page_size": 500},
                    headers=headers,
                )
                resp.raise_for_status()
                result = resp.json()
                inner = (result.get("data") or {}) if isinstance(result, dict) else {}
                members = []
                if isinstance(inner, dict):
                    members = inner.get("member_list") or inner.get("members") or []
                elif isinstance(inner, list):
                    members = inner
                for m in members:
                    uid = m.get("user_id") or m.get("acctid") or m.get("wxid") or ""
                    if uid and uid not in seen:
                        seen[uid] = {
                            "wxid": uid,
                            "nickname": m.get("realname") or m.get("nickname") or m.get("room_nickname") or m.get("username") or "",
                            "avatar": m.get("avatar") or m.get("small_avatar") or "",
                        }
            except Exception as exc:
                _room_logger.warning("拉取群 %s 成员失败: %s", rid, exc)

    return json_response(data=list(seen.values()))


@router.get("/employee-accounts", summary="获取已标记的员工企微账号")
def get_employee_accounts(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _ensure_employee_accounts_table(db)
    rows = db.execute(text(
        "SELECT wxid, nickname, created_at FROM wechat_employee_accounts ORDER BY id ASC"
    )).mappings().all()
    return json_response(data=[dict(r) for r in rows])


class SaveEmployeeAccountsReq(BaseModel):
    accounts: list[dict]


@router.post("/employee-accounts", summary="保存员工企微账号列表")
def save_employee_accounts(
    data: SaveEmployeeAccountsReq,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _ensure_employee_accounts_table(db)
    try:
        db.execute(text("DELETE FROM wechat_employee_accounts"))
        for acc in data.accounts:
            wxid = (acc.get("wxid") or "").strip()
            if not wxid:
                continue
            db.execute(text(
                "INSERT IGNORE INTO wechat_employee_accounts (wxid, nickname) VALUES (:wxid, :nickname)"
            ), {"wxid": wxid, "nickname": acc.get("nickname") or ""})
        db.commit()
        return json_response(message="保存成功")
    except Exception as exc:
        db.rollback()
        return json_response(code=500, message=f"保存失败: {exc}")
