#!/usr/bin/env python3
"""检查用户权限配置"""
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from app.config import settings

# 创建数据库连接
engine = create_engine(settings.DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)
db = SessionLocal()

print("=== 检查权限表 ===")
result = db.execute(text("SELECT id, code, name FROM permissions ORDER BY id"))
permissions = result.fetchall()
print(f"共有 {len(permissions)} 个权限:")
for p in permissions:
    print(f"  ID={p[0]}, code={p[1]}, name={p[2]}")

print("\n=== 检查角色权限关联 ===")
result = db.execute(text("""
    SELECT r.id, r.name, r.code, COUNT(rp.permission_id) as perm_count
    FROM roles r
    LEFT JOIN role_permissions rp ON r.id = rp.role_id
    GROUP BY r.id, r.name, r.code
"""))
roles = result.fetchall()
print(f"共有 {len(roles)} 个角色:")
for r in roles:
    print(f"  角色ID={r[0]}, name={r[1]}, code={r[2]}, 权限数={r[3]}")

print("\n=== 检查super_admin角色的具体权限 ===")
result = db.execute(text("""
    SELECT p.code, p.name
    FROM permissions p
    INNER JOIN role_permissions rp ON p.id = rp.permission_id
    WHERE rp.role_id = 1
    ORDER BY p.code
"""))
admin_perms = result.fetchall()
print(f"super_admin角色有 {len(admin_perms)} 个权限:")
for p in admin_perms:
    print(f"  - {p[0]} ({p[1]})")

print("\n=== 检查用户1的角色 ===")
result = db.execute(text("""
    SELECT r.code, r.name
    FROM roles r
    INNER JOIN user_roles ur ON r.id = ur.role_id
    WHERE ur.user_id = 1
"""))
user_roles = result.fetchall()
print(f"用户1有 {len(user_roles)} 个角色:")
for r in user_roles:
    print(f"  - {r[0]} ({r[1]})")

db.close()
