from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import Optional

from app.database import get_db
from app.models import Role, Permission, RolePermission, UserRole, User
from app.dependencies import check_permission
from app.schemas import RoleCreate, RoleUpdate
from app.utils.redis_client import redis_client

router = APIRouter(tags=["角色管理"])


def json_response(code=200, message="success", data=None):
    resp = {"code": code, "message": message}
    if data is not None:
        resp["data"] = data
    return resp


def build_permission_tree(permissions, parent_id=0):
    return [
        {
            "id": item.id,
            "parent_id": item.parent_id,
            "name": item.name,
            "code": item.code,
            "type": item.type,
            "path": item.path,
            "icon": item.icon,
            "sort": item.sort,
            "status": item.status,
            "children": build_permission_tree(permissions, item.id)
        }
        for item in permissions if item.parent_id == parent_id
    ]


@router.get("", summary="获取角色列表")
async def get_role_list(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, alias="page_size", ge=1, le=100),
    keyword: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(check_permission("system:role:list"))
):
    query = db.query(Role)
    if keyword:
        like_value = f"%{keyword}%"
        query = query.filter((Role.name.like(like_value)) | (Role.code.like(like_value)))

    total = query.count()
    roles = query.order_by(Role.sort.asc(), Role.created_at.asc()).offset((page - 1) * page_size).limit(page_size).all()

    role_ids = [item.id for item in roles]
    user_count_map = {}
    if role_ids:
        rows = db.query(UserRole.role_id, func.count(UserRole.user_id)).filter(UserRole.role_id.in_(role_ids)).group_by(UserRole.role_id).all()
        user_count_map = {role_id: count for role_id, count in rows}

    result = [
        {
            "id": item.id,
            "name": item.name,
            "code": item.code,
            "description": item.description,
            "status": item.status,
            "sort": item.sort,
            "created_at": item.created_at,
            "user_count": user_count_map.get(item.id, 0)
        }
        for item in roles
    ]

    return json_response(data={"list": result, "total": total, "page": page, "pageSize": page_size})


@router.get("/all", summary="获取所有角色")
async def get_all_roles(
    db: Session = Depends(get_db),
    current_user: User = Depends(check_permission("system:role:list"))
):
    roles = db.query(Role).filter(Role.status == 1).order_by(Role.sort.asc()).all()
    result = [
        {
            "id": item.id,
            "name": item.name,
            "code": item.code,
            "description": item.description,
            "status": item.status,
        }
        for item in roles
    ]
    return json_response(data=result)


@router.get("/permissions", summary="获取权限树")
async def get_permissions(
    db: Session = Depends(get_db),
    current_user: User = Depends(check_permission("system:role:list"))
):
    permissions = db.query(Permission).order_by(Permission.sort.asc()).all()
    return json_response(data=build_permission_tree(permissions))


@router.get("/{role_id}", summary="获取角色详情")
async def get_role_by_id(
    role_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(check_permission("system:role:list"))
):
    role = db.query(Role).filter(Role.id == role_id).first()
    if not role:
        raise HTTPException(status_code=404, detail="角色不存在")

    permission_ids = [item.permission_id for item in db.query(RolePermission.permission_id).filter(RolePermission.role_id == role_id).all()]
    return json_response(data={
        "id": role.id,
        "name": role.name,
        "code": role.code,
        "description": role.description,
        "status": role.status,
        "sort": role.sort,
        "created_at": role.created_at,
        "permissionIds": permission_ids
    })


@router.post("", summary="创建角色")
async def create_role(
    payload: RoleCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(check_permission("system:role:add"))
):
    existing = db.query(Role).filter(Role.code == payload.code).first()
    if existing:
        raise HTTPException(status_code=400, detail="角色编码已存在")

    role = Role(name=payload.name, code=payload.code, description=payload.description, sort=payload.sort or 0)
    db.add(role)
    db.flush()

    for permission_id in payload.permission_ids or []:
        db.add(RolePermission(role_id=role.id, permission_id=permission_id))

    db.commit()
    return json_response(message="创建成功", data={"id": role.id, "name": role.name, "code": role.code})


@router.put("/{role_id}", summary="更新角色")
async def update_role(
    role_id: int,
    payload: RoleUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(check_permission("system:role:edit"))
):
    role = db.query(Role).filter(Role.id == role_id).first()
    if not role:
        raise HTTPException(status_code=404, detail="角色不存在")

    if payload.name is not None:
        role.name = payload.name
    if payload.description is not None:
        role.description = payload.description
    if payload.status is not None:
        role.status = payload.status
    if payload.sort is not None:
        role.sort = payload.sort

    if payload.permission_ids is not None:
        db.query(RolePermission).filter(RolePermission.role_id == role_id).delete()
        for permission_id in payload.permission_ids:
            db.add(RolePermission(role_id=role_id, permission_id=permission_id))

    db.commit()

    user_ids = [item.user_id for item in db.query(UserRole.user_id).filter(UserRole.role_id == role_id).all()]
    for user_id in user_ids:
        redis_client.delete(f"user:permissions:{user_id}")

    return json_response(message="更新成功")


@router.delete("/{role_id}", summary="删除角色")
async def delete_role(
    role_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(check_permission("system:role:delete"))
):
    role = db.query(Role).filter(Role.id == role_id).first()
    if not role:
        raise HTTPException(status_code=404, detail="角色不存在")
    if role.code == "super_admin":
        raise HTTPException(status_code=400, detail="不能删除超级管理员角色")

    user_ids = [item.user_id for item in db.query(UserRole.user_id).filter(UserRole.role_id == role_id).all()]
    db.query(RolePermission).filter(RolePermission.role_id == role_id).delete()
    db.query(UserRole).filter(UserRole.role_id == role_id).delete()
    db.delete(role)
    db.commit()

    for user_id in user_ids:
        redis_client.delete(f"user:permissions:{user_id}")

    return json_response(message="删除成功")
