from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import or_, func
from typing import Optional
from app.database import get_db
from app.models import User, UserRole, Role
from app.schemas import UserCreate, UserUpdate, UserResponse, PageResponse
from app.dependencies import get_current_user, check_permission, get_user_permission_codes
from app.utils.security import get_password_hash
from app.utils.redis_client import redis_client

router = APIRouter(tags=["用户管理"])


@router.get("", response_model=PageResponse, summary="获取用户列表")
async def get_user_list(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(10, ge=1, le=100, description="每页数量"),
    keyword: Optional[str] = Query(None, description="搜索关键词"),
    db: Session = Depends(get_db),
    current_user: User = Depends(check_permission("system:user:list"))
):
    """
    获取用户列表（分页）

    - **page**: 页码，从1开始
    - **page_size**: 每页数量，最大100
    - **keyword**: 搜索关键词，支持用户名、姓名、邮箱模糊搜索
    """
    query = db.query(User).filter(User.deleted_at == None)

    # 关键词搜索
    if keyword:
        query = query.filter(
            or_(
                User.username.like(f"%{keyword}%"),
                User.real_name.like(f"%{keyword}%"),
                User.email.like(f"%{keyword}%")
            )
        )

    # 统计总数
    total = query.count()

    # 分页查询
    users = query.order_by(User.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()

    user_ids = [u.id for u in users]
    role_map: dict[int, dict[str, list]] = {}
    if user_ids:
        role_rows = db.query(
            UserRole.user_id,
            Role.id,
            Role.code,
            Role.name
        ).join(Role, Role.id == UserRole.role_id).filter(UserRole.user_id.in_(user_ids)).all()

        for user_id, role_id, role_code, role_name in role_rows:
            if user_id not in role_map:
                role_map[user_id] = {"ids": [], "codes": [], "names": []}
            role_map[user_id]["ids"].append(role_id)
            role_map[user_id]["codes"].append(role_code)
            role_map[user_id]["names"].append(role_name)

    # 查询每个用户的角色
    user_list = []
    for user in users:
        role_info = role_map.get(user.id, {"ids": [], "codes": [], "names": []})

        user_list.append({
            "id": user.id,
            "username": user.username,
            "real_name": user.real_name,
            "email": user.email,
            "phone": user.phone,
            "avatar": user.avatar,
            "status": user.status,
            "last_login_time": user.last_login_time,
            "created_at": user.created_at,
            "roles": role_info["codes"],
            "role_ids": role_info["ids"],
            "role_names": role_info["names"]
        })

    return PageResponse(
        data={
            "list": user_list,
            "total": total,
            "page": page,
            "page_size": page_size
        }
    )


@router.get("/roles/options", response_model=dict, summary="用户管理角色选项")
async def get_user_role_options(
    db: Session = Depends(get_db),
    current_user: User = Depends(check_permission("system:user:edit"))
):
    roles = db.query(Role).filter(Role.status == 1).order_by(Role.sort.asc(), Role.created_at.asc()).all()
    return {
        "code": 200,
        "message": "success",
        "data": [
            {
                "id": role.id,
                "name": role.name,
                "code": role.code,
            }
            for role in roles
        ]
    }


@router.get("/{user_id}", response_model=UserResponse, summary="获取用户详情")
async def get_user_by_id(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(check_permission("system:user:list"))
):
    """
    根据用户ID获取用户详细信息

    - **user_id**: 用户ID
    """
    user = db.query(User).filter(User.id == user_id, User.deleted_at == None).first()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")

    roles = db.query(Role.code).join(UserRole).filter(UserRole.user_id == user.id).all()
    role_codes = [role.code for role in roles]
    permission_codes = get_user_permission_codes(db=db, user_id=user.id)

    return UserResponse(
        id=user.id,
        username=user.username,
        real_name=user.real_name,
        email=user.email,
        phone=user.phone,
        avatar=user.avatar,
        status=user.status,
        last_login_time=user.last_login_time,
        created_at=user.created_at,
        roles=role_codes,
        permissions=permission_codes
    )


@router.post("", response_model=dict, summary="创建用户")
async def create_user(
    user_data: UserCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(check_permission("system:user:add"))
):
    """
    创建新用户

    - **username**: 用户名（唯一）
    - **password**: 密码
    - **real_name**: 真实姓名
    - **email**: 邮箱（可选）
    - **phone**: 手机号（可选）
    - **role_ids**: 角色ID列表（可选）
    """
    # 检查用户名是否已存在
    existing_user = db.query(User).filter(
        User.username == user_data.username,
        User.deleted_at == None
    ).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="用户名已存在")

    # 创建用户
    hashed_password = get_password_hash(user_data.password)
    new_user = User(
        username=user_data.username,
        password=hashed_password,
        real_name=user_data.real_name,
        email=user_data.email,
        phone=user_data.phone
    )
    db.add(new_user)
    db.flush()

    # 分配角色
    if user_data.role_ids:
        for role_id in user_data.role_ids:
            user_role = UserRole(user_id=new_user.id, role_id=role_id)
            db.add(user_role)

    db.commit()

    return {"code": 200, "message": "创建成功", "data": {"id": new_user.id}}


@router.put("/{user_id}", response_model=dict, summary="更新用户")
async def update_user(
    user_id: int,
    user_data: UserUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(check_permission("system:user:edit"))
):
    """
    更新用户信息

    - **user_id**: 用户ID
    - **real_name**: 真实姓名（可选）
    - **email**: 邮箱（可选）
    - **phone**: 手机号（可选）
    - **avatar**: 头像（可选）
    - **status**: 状态（可选）
    - **role_ids**: 角色ID列表（可选）
    """
    user = db.query(User).filter(User.id == user_id, User.deleted_at == None).first()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")

    # 更新基本信息
    if user_data.real_name is not None:
        user.real_name = user_data.real_name
    if user_data.email is not None:
        user.email = user_data.email
    if user_data.phone is not None:
        user.phone = user_data.phone
    if user_data.avatar is not None:
        user.avatar = user_data.avatar
    if user_data.status is not None:
        user.status = user_data.status

    # 更新角色关联
    if user_data.role_ids is not None:
        db.query(UserRole).filter(UserRole.user_id == user_id).delete()
        for role_id in user_data.role_ids:
            user_role = UserRole(user_id=user_id, role_id=role_id)
            db.add(user_role)

    db.commit()

    # 清除用户缓存
    redis_client.delete(f"user:{user_id}")
    redis_client.delete(f"user:permissions:{user_id}")

    return {"code": 200, "message": "更新成功"}


@router.delete("/{user_id}", response_model=dict, summary="删除用户")
async def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(check_permission("system:user:delete"))
):
    """
    删除用户（软删除）

    - **user_id**: 用户ID
    """
    user = db.query(User).filter(User.id == user_id, User.deleted_at == None).first()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")

    # 软删除
    user.deleted_at = func.now()
    db.commit()

    # 清除用户缓存
    redis_client.delete(f"user:{user_id}")
    redis_client.delete(f"user:permissions:{user_id}")

    return {"code": 200, "message": "删除成功"}
