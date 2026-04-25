from pydantic import BaseModel, EmailStr
from typing import Optional, List
from datetime import datetime


# 用户相关数据模型
class UserBase(BaseModel):
    """用户基础模型"""
    username: str  # 用户名
    real_name: str  # 真实姓名
    email: Optional[EmailStr] = None  # 邮箱
    phone: Optional[str] = None  # 手机号


class UserCreate(UserBase):
    """创建用户请求模型"""
    password: str  # 密码
    role_ids: Optional[List[int]] = []  # 角色ID列表


class UserUpdate(BaseModel):
    """更新用户请求模型"""
    real_name: Optional[str] = None  # 真实姓名
    email: Optional[EmailStr] = None  # 邮箱
    phone: Optional[str] = None  # 手机号
    avatar: Optional[str] = None  # 头像
    status: Optional[int] = None  # 状态
    role_ids: Optional[List[int]] = None  # 角色ID列表


class UserResponse(UserBase):
    """用户响应模型"""
    id: int  # 用户ID
    avatar: Optional[str] = None  # 头像
    status: int  # 状态
    last_login_time: Optional[datetime] = None  # 最后登录时间
    created_at: datetime  # 创建时间
    roles: Optional[List[str]] = []  # 角色列表
    permissions: Optional[List[str]] = []  # 权限编码列表

    class Config:
        from_attributes = True


# 认证相关数据模型
class LoginRequest(BaseModel):
    """登录请求模型"""
    username: str  # 用户名
    password: str  # 密码


class LoginResponse(BaseModel):
    """登录响应模型"""
    access_token: str  # 访问令牌
    token_type: str = "bearer"  # 令牌类型
    user: UserResponse  # 用户信息


class TokenData(BaseModel):
    """令牌数据模型"""
    user_id: int  # 用户ID
    username: str  # 用户名


# 角色相关数据模型
class RoleBase(BaseModel):
    """角色基础模型"""
    name: str  # 角色名称
    code: str  # 角色编码
    description: Optional[str] = None  # 角色描述
    sort: Optional[int] = 0  # 排序


class RoleCreate(RoleBase):
    """创建角色请求模型"""
    permission_ids: Optional[List[int]] = []  # 权限ID列表


class RoleUpdate(BaseModel):
    """更新角色请求模型"""
    name: Optional[str] = None  # 角色名称
    description: Optional[str] = None  # 角色描述
    status: Optional[int] = None  # 状态
    sort: Optional[int] = None  # 排序
    permission_ids: Optional[List[int]] = None  # 权限ID列表


class RoleResponse(RoleBase):
    """角色响应模型"""
    id: int  # 角色ID
    status: int  # 状态
    created_at: datetime  # 创建时间

    class Config:
        from_attributes = True


# 权限相关数据模型
class PermissionBase(BaseModel):
    """权限基础模型"""
    parent_id: int = 0  # 父级ID
    name: str  # 权限名称
    code: str  # 权限编码
    type: int  # 类型：1-菜单 2-按钮 3-接口
    path: Optional[str] = None  # 路由路径
    method: Optional[str] = None  # HTTP方法
    icon: Optional[str] = None  # 图标
    sort: Optional[int] = 0  # 排序


class PermissionCreate(PermissionBase):
    """创建权限请求模型"""
    pass


class PermissionUpdate(BaseModel):
    """更新权限请求模型"""
    name: Optional[str] = None  # 权限名称
    path: Optional[str] = None  # 路由路径
    method: Optional[str] = None  # HTTP方法
    icon: Optional[str] = None  # 图标
    sort: Optional[int] = None  # 排序
    status: Optional[int] = None  # 状态


class PermissionResponse(PermissionBase):
    """权限响应模型"""
    id: int  # 权限ID
    status: int  # 状态
    created_at: datetime  # 创建时间

    class Config:
        from_attributes = True


# 通用响应数据模型
class Response(BaseModel):
    """通用响应模型"""
    code: int = 200  # 状态码
    message: str = "success"  # 消息


# 企业微信实例相关模型
class WechatInstanceBase(BaseModel):
    wxid: str
    name: str
    api_base_url: str
    api_key: Optional[str] = None

class WechatInstanceCreate(WechatInstanceBase):
    pass

class WechatInstanceUpdate(BaseModel):
    name: Optional[str] = None
    api_base_url: Optional[str] = None
    api_key: Optional[str] = None
    status: Optional[int] = None

class WechatInstanceResponse(WechatInstanceBase):
    id: int
    status: int
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True

# 群聊监听配置相关模型
class WechatListenerBase(BaseModel):
    instance_id: int
    room_id: str
    room_name: Optional[str] = None
    is_enabled: int = 1
    description: Optional[str] = None

class WechatListenerUpdate(BaseModel):
    is_enabled: Optional[int] = None
    description: Optional[str] = None

class WechatListenerResponse(WechatListenerBase):
    id: int
    created_at: datetime
    updated_at: Optional[datetime] = None
    instance_name: Optional[str] = None
    wxid: Optional[str] = None

    class Config:
        from_attributes = True

class WechatBatchUpdateListeners(BaseModel):
    instanceId: int
    roomIds: List[str]
    isEnabled: int
    data: Optional[dict] = None  # 数据


class PageResponse(BaseModel):
    """分页响应模型"""
    code: int = 200  # 状态码
    message: str = "success"  # 消息
    data: dict  # 数据（包含list、total、page、page_size）
