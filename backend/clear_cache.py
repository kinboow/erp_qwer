#!/usr/bin/env python3
"""清除Redis权限缓存"""
import redis
from app.config import settings

# 连接Redis
client = redis.Redis(
    host=settings.REDIS_HOST,
    port=settings.REDIS_PORT,
    password=settings.REDIS_PASSWORD if settings.REDIS_PASSWORD else None,
    db=settings.REDIS_DB,
    decode_responses=True
)

# 查找并删除所有权限缓存
keys = client.keys("user:permissions:*")
if keys:
    deleted = client.delete(*keys)
    print(f"已删除 {deleted} 个权限缓存键")
    for key in keys:
        print(f"  - {key}")
else:
    print("没有找到权限缓存键")

print("\n缓存已清除，用户下次请求时将从数据库重新加载权限")
