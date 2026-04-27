import asyncio

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import Optional, List
from pydantic import BaseModel

from app.database import get_db
from app.models import User
from app.dependencies import get_current_user
from app.services.downstream_support import ensure_downstream_support_tables
from app.services.customer_sync import sync_customers

router = APIRouter(tags=["客户管理"])


class CustomerWechatRoomDto(BaseModel):
    instance_id: int
    room_id: str
    room_name: Optional[str] = None


class CustomerCreateDto(BaseModel):
    customer_name: str
    contact_person: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    company_name: Optional[str] = None
    address: Optional[str] = None
    remark: Optional[str] = None
    erp_customer_id: Optional[str] = None
    status: Optional[int] = 1
    wechat_rooms: Optional[List[CustomerWechatRoomDto]] = []


class CustomerUpdateDto(BaseModel):
    customer_name: Optional[str] = None
    contact_person: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    company_name: Optional[str] = None
    address: Optional[str] = None
    remark: Optional[str] = None
    erp_customer_id: Optional[str] = None
    status: Optional[int] = None
    wechat_rooms: Optional[List[CustomerWechatRoomDto]] = None


def json_response(code=200, message="success", data=None):
    resp = {"code": code, "message": message}
    if data is not None:
        resp["data"] = data
    return resp


def get_rooms_map(db: Session, customer_ids: List[int]):
    room_map = {}
    if not customer_ids:
        return room_map

    sql = text(
        f"SELECT customer_id, instance_id, room_id, room_name FROM downstream_customer_wechat_rooms WHERE customer_id IN ({','.join([str(item) for item in customer_ids])}) ORDER BY id ASC"
    )
    rows = db.execute(sql).mappings().all()
    for row in rows:
        room_map.setdefault(row["customer_id"], []).append({
            "instance_id": row["instance_id"],
            "room_id": row["room_id"],
            "room_name": row["room_name"]
        })
    return room_map


def get_customer_rooms(db: Session, customer_id: int):
    rows = db.execute(
        text("SELECT instance_id, room_id, room_name FROM downstream_customer_wechat_rooms WHERE customer_id = :customer_id ORDER BY id ASC"),
        {"customer_id": customer_id}
    ).mappings().all()
    return [
        {"instance_id": row["instance_id"], "room_id": row["room_id"], "room_name": row["room_name"]}
        for row in rows
    ]


def replace_customer_rooms(db: Session, customer_id: int, rooms: Optional[List[CustomerWechatRoomDto]]):
    db.execute(text("DELETE FROM downstream_customer_wechat_rooms WHERE customer_id = :customer_id"), {"customer_id": customer_id})
    if not rooms:
        return
    for room in rooms:
        if not room.instance_id or not room.room_id:
            continue
        db.execute(
            text("INSERT INTO downstream_customer_wechat_rooms (customer_id, instance_id, room_id, room_name) VALUES (:customer_id, :instance_id, :room_id, :room_name)"),
            {
                "customer_id": customer_id,
                "instance_id": room.instance_id,
                "room_id": room.room_id,
                "room_name": room.room_name or ""
            }
        )


@router.post("/sync", summary="从ERP同步客户列表")
async def api_sync_customers(
    request: Request,
    current_user: User = Depends(get_current_user),
):
    erp_client = getattr(request.app.state, "erp_client", None)
    if not erp_client:
        raise HTTPException(status_code=503, detail="ERP 客户端未初始化，请先配置 ERP 连接")
    try:
        result = await sync_customers(erp_client)
        return json_response(message="客户同步完成", data=result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"同步失败: {str(e)}")


@router.get("", summary="获取客户列表")
async def get_customer_list(
    page: int = Query(1, ge=1),
    pageSize: int = Query(20, ge=1, le=200),
    keyword: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    ensure_downstream_support_tables(db)

    # 后台刷新关联群聊的 room_name（不阻塞响应）
    async def _bg_sync_room_names():
        from app.database import SessionLocal
        from app.routers.wechat_config import sync_room_names_to_customers
        bg_db = SessionLocal()
        try:
            await sync_room_names_to_customers(bg_db)
        except Exception:
            pass
        finally:
            bg_db.close()
    try:
        asyncio.create_task(_bg_sync_room_names())
    except Exception:
        pass
    params = {}
    where_sql = "WHERE deleted_at IS NULL"
    if keyword:
        where_sql += " AND (customer_name LIKE :keyword OR contact_person LIKE :keyword OR phone LIKE :keyword OR company_name LIKE :keyword OR erp_customer_id LIKE :keyword OR salesperson LIKE :keyword OR short_code LIKE :keyword OR address LIKE :keyword)"
        params["keyword"] = f"%{keyword}%"

    list_sql = text(f"SELECT id, customer_name, contact_person, phone, telephone, email, company_name, address, remark, erp_customer_id, status, salesperson, customer_type, shipping_address, shipping_phone, short_code, nature, credit_limit, synced_at, created_at, updated_at FROM downstream_customers {where_sql} ORDER BY CAST(erp_customer_id AS UNSIGNED) ASC, id ASC LIMIT :limit OFFSET :offset")
    params.update({"limit": pageSize, "offset": (page - 1) * pageSize})
    rows = db.execute(list_sql, params).mappings().all()

    count_params = dict(params)
    count_params.pop("limit", None)
    count_params.pop("offset", None)
    count_sql = text(f"SELECT COUNT(*) as total FROM downstream_customers {where_sql}")
    total = db.execute(count_sql, count_params).mappings().first()["total"]

    customer_ids = [row["id"] for row in rows]
    room_map = get_rooms_map(db, customer_ids)
    result = []
    for row in rows:
        item = dict(row)
        item["wechat_rooms"] = room_map.get(row["id"], [])
        result.append(item)

    return json_response(message="获取成功", data={"list": result, "total": total, "page": page, "pageSize": pageSize})


@router.get("/{customer_id}", summary="获取客户详情")
async def get_customer_by_id(
    customer_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    ensure_downstream_support_tables(db)
    row = db.execute(
        text("SELECT id, customer_name, contact_person, phone, email, company_name, address, remark, erp_customer_id, status, created_at, updated_at FROM downstream_customers WHERE id = :customer_id AND deleted_at IS NULL"),
        {"customer_id": customer_id}
    ).mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="客户不存在")

    result = dict(row)
    result["wechat_rooms"] = get_customer_rooms(db, customer_id)
    return json_response(message="获取成功", data=result)


@router.post("", summary="创建客户")
async def create_customer(
    payload: CustomerCreateDto,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    ensure_downstream_support_tables(db)
    if not payload.customer_name:
        raise HTTPException(status_code=400, detail="客户名称不能为空")

    result = db.execute(
        text("INSERT INTO downstream_customers (customer_name, contact_person, phone, email, company_name, address, remark, erp_customer_id, status) VALUES (:customer_name, :contact_person, :phone, :email, :company_name, :address, :remark, :erp_customer_id, :status)"),
        {
            "customer_name": payload.customer_name,
            "contact_person": payload.contact_person or "",
            "phone": payload.phone or "",
            "email": payload.email or "",
            "company_name": payload.company_name or "",
            "address": payload.address or "",
            "remark": payload.remark or "",
            "erp_customer_id": payload.erp_customer_id or "",
            "status": payload.status or 1,
        }
    )
    customer_id = result.lastrowid
    replace_customer_rooms(db, customer_id, payload.wechat_rooms)
    db.commit()
    return json_response(message="创建成功", data={"id": customer_id, "customer_name": payload.customer_name})


@router.put("/{customer_id}", summary="更新客户")
async def update_customer(
    customer_id: int,
    payload: CustomerUpdateDto,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    ensure_downstream_support_tables(db)
    row = db.execute(
        text("SELECT erp_customer_id FROM downstream_customers WHERE id = :cid AND deleted_at IS NULL"),
        {"cid": customer_id},
    ).mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="客户不存在")
    is_erp = bool(row["erp_customer_id"])

    # ERP 同步客户只允许更新关联群聊，不允许改其他字段
    updates = []
    params = {"customer_id": customer_id}
    for key in ["customer_name", "contact_person", "phone", "email", "company_name", "address", "remark", "erp_customer_id", "status"]:
        value = getattr(payload, key)
        if value is not None:
            if is_erp:
                raise HTTPException(status_code=403, detail="ERP同步的客户基本信息不可修改，仅可绑定群聊")
            updates.append(f"{key} = :{key}")
            params[key] = value

    if updates:
        db.execute(text(f"UPDATE downstream_customers SET {', '.join(updates)}, updated_at = NOW() WHERE id = :customer_id AND deleted_at IS NULL"), params)

    if payload.wechat_rooms is not None:
        replace_customer_rooms(db, customer_id, payload.wechat_rooms)

    db.commit()
    return json_response(message="更新成功")


@router.delete("/{customer_id}", summary="删除客户")
async def delete_customer(
    customer_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    row = db.execute(
        text("SELECT erp_customer_id FROM downstream_customers WHERE id = :cid AND deleted_at IS NULL"),
        {"cid": customer_id},
    ).mappings().first()
    if row and row["erp_customer_id"]:
        raise HTTPException(status_code=403, detail="ERP同步的客户数据不可删除")
    db.execute(text("UPDATE downstream_customers SET deleted_at = NOW() WHERE id = :customer_id"), {"customer_id": customer_id})
    db.execute(text("DELETE FROM downstream_customer_wechat_rooms WHERE customer_id = :customer_id"), {"customer_id": customer_id})
    db.commit()
    return json_response(message="删除成功")


# ---------- 用户偏好设置 ----------

class PrefUpdateDto(BaseModel):
    value: str


@router.get("/preferences/{pref_key}", summary="获取用户偏好")
async def get_preference(
    pref_key: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    ensure_downstream_support_tables(db)
    row = db.execute(
        text("SELECT pref_value FROM user_preferences WHERE user_id = :uid AND pref_key = :key"),
        {"uid": current_user.id, "key": pref_key},
    ).mappings().first()
    return json_response(data={"value": row["pref_value"] if row else None})


@router.put("/preferences/{pref_key}", summary="保存用户偏好")
async def save_preference(
    pref_key: str,
    payload: PrefUpdateDto,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    ensure_downstream_support_tables(db)
    db.execute(
        text(
            "INSERT INTO user_preferences (user_id, pref_key, pref_value) "
            "VALUES (:uid, :key, :val) "
            "ON DUPLICATE KEY UPDATE pref_value = :val"
        ),
        {"uid": current_user.id, "key": pref_key, "val": payload.value},
    )
    db.commit()
    return json_response(message="保存成功")
