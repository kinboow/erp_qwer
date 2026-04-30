from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session
from datetime import datetime
from app.database import get_db
from app.models import User, UserRole, Role
from app.schemas import LoginRequest, LoginResponse, UserResponse, TokenData
from app.utils.security import verify_password, create_access_token
from app.utils.redis_client import redis_client
from app.dependencies import get_current_user, get_user_permission_codes
import json

router = APIRouter(tags=["认证管理"])


@router.post("/login", summary="用户登录")
async def login(request: Request, login_data: LoginRequest, db: Session = Depends(get_db)):
    """
    用户登录接口

    - **username**: 用户名
    - **password**: 密码
    """
    # 查询用户
    user = db.query(User).filter(
        User.username == login_data.username,
        User.deleted_at == None
    ).first()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误"
        )

    # 检查用户状态
    if user.status == 0:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="账号已被禁用"
        )

    # 验证密码
    if not verify_password(login_data.password, user.password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误"
        )

    # 更新最后登录信息
    user.last_login_time = datetime.now()
    user.last_login_ip = request.client.host
    db.commit()

    # 生成访问令牌
    access_token = create_access_token(
        data={"user_id": user.id, "username": user.username}
    )

    # 查询用户角色
    roles = db.query(Role.code).join(UserRole).filter(
        UserRole.user_id == user.id
    ).all()
    role_codes = [role.code for role in roles]
    permission_codes = get_user_permission_codes(db=db, user_id=user.id)

    # 缓存用户信息（2小时）
    user_info = {
        "id": user.id,
        "username": user.username,
        "real_name": user.real_name,
        "email": user.email,
        "roles": role_codes
    }
    redis_client.set(f"user:{user.id}", json.dumps(user_info), ex=7200)

    return {
        "code": 200,
        "message": "登录成功",
        "data": {
            "accessToken": access_token,
            "user": {
                "id": user.id,
                "username": user.username,
                "real_name": user.real_name,
                "email": user.email,
                "phone": user.phone,
                "avatar": user.avatar,
                "status": user.status,
                "last_login_time": str(user.last_login_time) if user.last_login_time else None,
                "created_at": str(user.created_at) if user.created_at else None,
                "roles": role_codes,
                "permissions": permission_codes
            }
        }
    }


@router.post("/logout", summary="用户登出")
async def logout(token: str = Depends(lambda: None)):
    """
    用户登出接口

    将当前令牌加入黑名单，使其失效
    """
    # 将token加入黑名单（7天）
    if token:
        redis_client.set(f"blacklist:{token}", "1", ex=604800)

    return {"code": 200, "message": "退出成功"}


@router.post("/verify-password", summary="验证当前用户密码")
async def verify_current_password(
    payload: dict,
    current_user: User = Depends(get_current_user),
):
    password = (payload.get("password") or "").strip()
    if not password:
        return {"code": 400, "message": "密码不能为空"}
    if not verify_password(password, current_user.password):
        return {"code": 403, "message": "密码错误"}
    return {"code": 200, "message": "验证通过"}


@router.get("/userinfo", response_model=UserResponse, summary="获取当前用户信息")
async def get_user_info(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """
    获取当前登录用户的详细信息

    需要在请求头中携带有效的访问令牌
    """
    # 查询用户角色
    roles = db.query(Role.code).join(UserRole).filter(
        UserRole.user_id == current_user.id
    ).all()
    role_codes = [role.code for role in roles]
    permission_codes = get_user_permission_codes(db=db, user_id=current_user.id)

    return UserResponse(
        id=current_user.id,
        username=current_user.username,
        real_name=current_user.real_name,
        email=current_user.email,
        phone=current_user.phone,
        avatar=current_user.avatar,
        status=current_user.status,
        last_login_time=current_user.last_login_time,
        created_at=current_user.created_at,
        roles=role_codes,
        permissions=permission_codes
    )
