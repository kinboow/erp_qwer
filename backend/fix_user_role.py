#!/usr/bin/env python3
"""修复用户1的角色分配"""
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

print("=== 修复用户1的角色 ===")

# 删除用户1的现有角色
result = db.execute(text("DELETE FROM user_roles WHERE user_id = 1"))
print(f"删除了用户1的旧角色关联")

# 分配super_admin角色(role_id=1)给用户1
result = db.execute(text("INSERT INTO user_roles (user_id, role_id) VALUES (1, 1)"))
db.commit()
print("已将用户1分配为super_admin角色")

# 验证
result = db.execute(text("""
    SELECT r.code, r.name
    FROM roles r
    INNER JOIN user_roles ur ON r.id = ur.role_id
    WHERE ur.user_id = 1
"""))
user_roles = result.fetchall()
print(f"\n用户1现在的角色:")
for r in user_roles:
    print(f"  - {r[0]} ({r[1]})")

db.close()
print("\n修复完成！")
