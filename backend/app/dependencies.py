from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from typing import Optional
import json
from app.database import get_db
from app.models import User
from app.utils.security import decode_access_token
from app.utils.redis_client import redis_client

security = HTTPBearer()

SUPER_ADMIN_ROLE_ALIASES = {
    "super_admin",
    "superadmin",
    "sys_admin",
    "系统超级管理员",
    "超级管理员",
}


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
) -> User:
    """获取当前用户"""
    token = credentials.credentials

    # 检查token是否在黑名单中
    if redis_client.exists(f"blacklist:{token}"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="令牌已失效"
        )

    # 解码token
    payload = decode_access_token(token)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效的认证凭证"
        )

    user_id: int = payload.get("user_id") or payload.get("userId")
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效的认证凭证"
        )

    # 查询用户
    user = db.query(User).filter(User.id == user_id, User.deleted_at == None).first()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户不存在"
        )

    if user.status == 0:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="账号已被禁用"
        )

    return user


def get_user_permission_codes(db: Session, user_id: int) -> list[str]:
    """获取用户权限编码（含缓存）"""
    from app.models import Permission, RolePermission, UserRole, Role

    role_rows = db.query(Role.code, Role.name).join(
        UserRole, Role.id == UserRole.role_id
    ).filter(
        UserRole.user_id == user_id
    ).all()
    role_tokens = {
        str(token).strip().lower()
        for row in role_rows
        for token in (row.code, row.name)
        if token
    }
    super_admin_aliases = {item.lower() for item in SUPER_ADMIN_ROLE_ALIASES}

    if role_tokens.intersection(super_admin_aliases):
        return ["*"]

    cache_key = f"user:permissions:{user_id}"
    permissions_json = redis_client.get(cache_key)
    if permissions_json:
        try:
            return json.loads(permissions_json)
        except Exception:
            redis_client.delete(cache_key)

    permission_rows = db.query(Permission.code).join(
        RolePermission, Permission.id == RolePermission.permission_id
    ).join(
        UserRole, RolePermission.role_id == UserRole.role_id
    ).join(
        Role, Role.id == UserRole.role_id
    ).filter(
        UserRole.user_id == user_id,
        Permission.status == 1,
        Role.status == 1
    ).distinct().all()

    permissions = [p.code for p in permission_rows]
    redis_client.set(cache_key, json.dumps(permissions), ex=3600)
    return permissions


def check_permission(required_permission: str):
    """检查权限装饰器"""
    async def permission_checker(
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
    ):
        permissions = get_user_permission_codes(db=db, user_id=current_user.id)

        if "*" in permissions:
            return current_user

        # 检查所需权限
        if required_permission not in permissions:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"权限不足，缺少权限：{required_permission}"
            )

        return current_user

    return permission_checker
