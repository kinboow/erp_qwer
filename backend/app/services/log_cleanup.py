"""
日志清理定时任务 —— 每天检查一次，删除 15 天前的日志记录。
清理范围：system_logs、operation_logs、message_logs
"""

import asyncio
import logging
from datetime import datetime, timedelta

from sqlalchemy import text

from app.database import SessionLocal

logger = logging.getLogger(__name__)

RETENTION_DAYS = 15
_cleanup_task = None


def _do_cleanup():
    """执行一次清理"""
    cutoff = (datetime.now() - timedelta(days=RETENTION_DAYS)).strftime("%Y-%m-%d %H:%M:%S")
    tables = [
        ("system_logs", "timestamp"),
        ("operation_logs", "created_at"),
    ]
    db = SessionLocal()
    try:
        for table, col in tables:
            try:
                result = db.execute(
                    text(f"DELETE FROM {table} WHERE {col} < :cutoff"),
                    {"cutoff": cutoff},
                )
                deleted = result.rowcount
                db.commit()
                if deleted > 0:
                    logger.info("[LogCleanup] 清理 %s: 删除 %d 条 (>%d天)", table, deleted, RETENTION_DAYS)
            except Exception as e:
                logger.warning("[LogCleanup] 清理 %s 失败: %s", table, e)
                try:
                    db.rollback()
                except Exception:
                    pass
    finally:
        db.close()


async def _cleanup_loop():
    """后台循环：每 24 小时清理一次"""
    # 启动后等 60 秒再首次执行，避免启动时竞争
    await asyncio.sleep(60)
    while True:
        try:
            _do_cleanup()
        except Exception as e:
            logger.warning("[LogCleanup] 异常: %s", e)
        await asyncio.sleep(24 * 3600)


def start_log_cleanup():
    """启动日志清理定时任务"""
    global _cleanup_task
    if _cleanup_task is None or _cleanup_task.done():
        _cleanup_task = asyncio.ensure_future(_cleanup_loop())
        logger.info("[LogCleanup] 日志清理定时任务已启动 (保留 %d 天)", RETENTION_DAYS)


def stop_log_cleanup():
    """停止日志清理定时任务"""
    global _cleanup_task
    if _cleanup_task and not _cleanup_task.done():
        _cleanup_task.cancel()
        _cleanup_task = None
