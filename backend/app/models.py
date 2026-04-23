from sqlalchemy import Column, Integer, String, DateTime, SmallInteger, Text, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base


class User(Base):
    """用户模型"""
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True, comment="用户ID")
    username = Column(String(50), unique=True, nullable=False, index=True, comment="用户名")
    password = Column(String(255), nullable=False, comment="密码")
    real_name = Column(String(50), nullable=False, comment="真实姓名")
    email = Column(String(100), unique=True, comment="邮箱")
    phone = Column(String(20), unique=True, comment="手机号")
    avatar = Column(String(255), comment="头像")
    status = Column(SmallInteger, default=1, comment="状态：0-禁用 1-启用")
    last_login_time = Column(DateTime, comment="最后登录时间")
    last_login_ip = Column(String(50), comment="最后登录IP")
    created_at = Column(DateTime, server_default=func.now(), comment="创建时间")
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), comment="更新时间")
    deleted_at = Column(DateTime, comment="删除时间")

    user_roles = relationship("UserRole", back_populates="user")


class Role(Base):
    """角色模型"""
    __tablename__ = "roles"

    id = Column(Integer, primary_key=True, index=True, comment="角色ID")
    name = Column(String(50), unique=True, nullable=False, comment="角色名称")
    code = Column(String(50), unique=True, nullable=False, index=True, comment="角色编码")
    description = Column(String(255), comment="角色描述")
    status = Column(SmallInteger, default=1, comment="状态：0-禁用 1-启用")
    sort = Column(Integer, default=0, comment="排序")
    created_at = Column(DateTime, server_default=func.now(), comment="创建时间")
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), comment="更新时间")

    role_permissions = relationship("RolePermission", back_populates="role")
    user_roles = relationship("UserRole", back_populates="role")


class Permission(Base):
    """权限模型"""
    __tablename__ = "permissions"

    id = Column(Integer, primary_key=True, index=True, comment="权限ID")
    parent_id = Column(Integer, default=0, comment="父级ID")
    name = Column(String(50), nullable=False, comment="权限名称")
    code = Column(String(100), unique=True, nullable=False, index=True, comment="权限编码")
    type = Column(SmallInteger, nullable=False, comment="类型：1-菜单 2-按钮 3-接口")
    path = Column(String(255), comment="路由路径")
    method = Column(String(10), comment="HTTP方法")
    icon = Column(String(50), comment="图标")
    sort = Column(Integer, default=0, comment="排序")
    status = Column(SmallInteger, default=1, comment="状态：0-禁用 1-启用")
    created_at = Column(DateTime, server_default=func.now(), comment="创建时间")
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), comment="更新时间")

    role_permissions = relationship("RolePermission", back_populates="permission")


class UserRole(Base):
    """用户角色关联模型"""
    __tablename__ = "user_roles"

    id = Column(Integer, primary_key=True, index=True, comment="ID")
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, comment="用户ID")
    role_id = Column(Integer, ForeignKey("roles.id", ondelete="CASCADE"), nullable=False, comment="角色ID")
    created_at = Column(DateTime, server_default=func.now(), comment="创建时间")

    user = relationship("User", back_populates="user_roles")
    role = relationship("Role", back_populates="user_roles")


class RolePermission(Base):
    """角色权限关联模型"""
    __tablename__ = "role_permissions"

    id = Column(Integer, primary_key=True, index=True, comment="ID")
    role_id = Column(Integer, ForeignKey("roles.id", ondelete="CASCADE"), nullable=False, comment="角色ID")
    permission_id = Column(Integer, ForeignKey("permissions.id", ondelete="CASCADE"), nullable=False, comment="权限ID")
    created_at = Column(DateTime, server_default=func.now(), comment="创建时间")

    role = relationship("Role", back_populates="role_permissions")
    permission = relationship("Permission", back_populates="role_permissions")


class OperationLog(Base):
    """操作日志模型"""
    __tablename__ = "operation_logs"

    id = Column(Integer, primary_key=True, index=True, comment="日志ID")
    user_id = Column(Integer, comment="用户ID")
    username = Column(String(50), comment="用户名")
    module = Column(String(50), comment="模块")
    action = Column(String(50), comment="操作")
    method = Column(String(10), comment="HTTP方法")
    path = Column(String(255), comment="请求路径")
    ip = Column(String(50), comment="IP地址")
    user_agent = Column(String(500), comment="用户代理")
    request_data = Column(Text, comment="请求数据")
    response_data = Column(Text, comment="响应数据")
    status = Column(SmallInteger, comment="状态：0-失败 1-成功")
    error_msg = Column(Text, comment="错误信息")
    duration = Column(Integer, comment="耗时(ms)")
    created_at = Column(DateTime, server_default=func.now(), comment="创建时间")


class WechatInstance(Base):
    """企业微信实例模型"""
    __tablename__ = "wechat_instances"

    id = Column(Integer, primary_key=True, index=True, comment="实例ID")
    wxid = Column(String(100), unique=True, nullable=False, index=True, comment="企业微信实例ID")
    name = Column(String(100), nullable=False, comment="实例名称")
    status = Column(SmallInteger, default=1, index=True, comment="状态: 0-离线 1-在线")
    api_base_url = Column(String(255), nullable=False, comment="API基础URL")
    api_key = Column(String(255), nullable=True, comment="API调用密钥(X-API-Key)")
    created_at = Column(DateTime, server_default=func.now(), comment="创建时间")
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), comment="更新时间")

    listeners = relationship("WechatRoomListener", back_populates="instance", cascade="all, delete-orphan")


class WechatRoomListener(Base):
    """群聊监听配置模型"""
    __tablename__ = "wechat_room_listeners"

    id = Column(Integer, primary_key=True, index=True, comment="配置ID")
    instance_id = Column(Integer, ForeignKey("wechat_instances.id", ondelete="CASCADE"), nullable=False, index=True, comment="企业微信实例ID")
    room_id = Column(String(100), nullable=False, comment="群聊ID")
    room_name = Column(String(200), comment="群聊名称")
    is_enabled = Column(SmallInteger, default=1, index=True, comment="是否启用监听: 0-禁用 1-启用")
    description = Column(String(500), comment="备注说明")
    created_at = Column(DateTime, server_default=func.now(), comment="创建时间")
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), comment="更新时间")

    instance = relationship("WechatInstance", back_populates="listeners")
