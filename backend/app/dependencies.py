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


def check_permission(required_permission: str):
    """检查权限装饰器"""
    async def permission_checker(
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
    ):
        # 检查用户是否是超级管理员（通过角色）
        from app.models import Role, UserRole
        user_roles = db.query(Role.code).join(
            UserRole, Role.id == UserRole.role_id
        ).filter(
            UserRole.user_id == current_user.id
        ).all()

        role_codes = [r.code for r in user_roles]

        # 超级管理员拥有所有权限
        if "super_admin" in role_codes:
            return current_user

        # 从缓存获取用户权限
        cache_key = f"user:permissions:{current_user.id}"
        permissions_json = redis_client.get(cache_key)

        if permissions_json:
            permissions = json.loads(permissions_json)
        else:
            # 从数据库查询权限
            from app.models import Permission, RolePermission
            permissions_query = db.query(Permission.code).join(
                RolePermission, Permission.id == RolePermission.permission_id
            ).join(
                UserRole, RolePermission.role_id == UserRole.role_id
            ).filter(
                UserRole.user_id == current_user.id,
                Permission.status == 1
            ).distinct()

            permissions = [p.code for p in permissions_query.all()]

            # 缓存权限（1小时）
            redis_client.set(cache_key, json.dumps(permissions), ex=3600)

        # 检查所需权限
        if required_permission not in permissions:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="权限不足"
            )

        return current_user

    return permission_checker
