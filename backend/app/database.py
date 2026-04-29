import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import TypeVar, Callable

from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from app.config import settings

# 创建数据库引擎
# pool_size=15 + max_overflow=10 → 最多 25 并发连接，避免同步阻塞时连接不够用
engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,    # 连接池预检查
    pool_recycle=3600,     # 连接回收时间（秒）
    pool_size=15,          # 常驻连接数
    max_overflow=10,       # 超出 pool_size 后允许的临时连接
    echo=False,            # 关闭 SQL 打印，减少 I/O 开销
)

# 创建会话工厂
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# 创建基础模型类
Base = declarative_base()

# 线程池：用于将同步 DB 操作从 asyncio 事件循环中卸载
_db_thread_pool = ThreadPoolExecutor(max_workers=8, thread_name_prefix="db-worker")

T = TypeVar("T")


async def run_in_threadpool(func: Callable[..., T], *args, **kwargs) -> T:
    """在线程池中执行同步阻塞函数，避免阻塞 asyncio 事件循环。

    用法::

        result = await run_in_threadpool(some_sync_db_function, db, param1, param2)
    """
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        _db_thread_pool,
        lambda: func(*args, **kwargs),
    )


def get_db():
    """获取数据库会话"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
