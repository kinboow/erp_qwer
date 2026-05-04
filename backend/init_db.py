"""
数据库初始化脚本
- 创建管理员角色 (super_admin)
- 创建管理员账号 (admin / admin123)
- 初始化 AI 配置（默认值，留空 API Key）
"""

from sqlalchemy import text
from app.database import SessionLocal
from app.models import Base, User, Role, UserRole
from app.utils.security import get_password_hash
from app.services.ai_config import ensure_ai_config_table, save_ai_config, _AI_CONFIG_DEFAULTS


def init():
    db = SessionLocal()
    try:
        # ── 1. 创建管理员角色 ────────────────────────────
        existing_role = db.query(Role).filter(Role.code == "super_admin").first()
        if existing_role:
            role = existing_role
            print(f"  角色已存在: {role.name} (id={role.id})")
        else:
            role = Role(
                name="超级管理员",
                code="super_admin",
                description="拥有系统所有权限",
                status=1,
                sort=0,
            )
            db.add(role)
            db.flush()
            print(f"  创建角色: {role.name} (id={role.id})")

        # ── 2. 创建管理员账号 ────────────────────────────
        existing_user = db.query(User).filter(
            User.username == "admin", User.deleted_at == None
        ).first()
        if existing_user:
            user = existing_user
            print(f"  用户已存在: {user.username} (id={user.id})")
        else:
            user = User(
                username="admin",
                password=get_password_hash("admin123"),
                real_name="管理员",
                status=1,
            )
            db.add(user)
            db.flush()
            print(f"  创建用户: {user.username} (id={user.id})")

        # ── 3. 绑定角色 ─────────────────────────────────
        existing_bind = db.query(UserRole).filter(
            UserRole.user_id == user.id, UserRole.role_id == role.id
        ).first()
        if existing_bind:
            print(f"  角色绑定已存在: user={user.id} -> role={role.id}")
        else:
            db.add(UserRole(user_id=user.id, role_id=role.id))
            print(f"  绑定角色: user={user.id} -> role={role.id}")

        db.commit()

        # ── 4. 初始化 AI 配置（默认值） ──────────────────
        ensure_ai_config_table(db)
        save_ai_config(db, _AI_CONFIG_DEFAULTS)
        print("  AI 配置已初始化（默认值，API Key 留空）")

        print("\n✅ 初始化完成！")
        print("   管理员账号: admin")
        print("   管理员密码: admin123")

    except Exception as exc:
        db.rollback()
        print(f"\n❌ 初始化失败: {exc}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    init()
