"""
日志清理模块 —— 定时清除 20 天以前的系统日志和 AI 调用日志。
注意：操作日志 (operation_logs) 和消息日志 (message_logs) 永远不清除。
"""

import logging
import threading
from datetime import datetime, timedelta

from sqlalchemy import text

from app.database import SessionLocal

logger = logging.getLogger(__name__)

_RETENTION_DAYS = 20
_INTERVAL_HOURS = 6  # 每 6 小时执行一次清理
_timer: threading.Timer | None = None


def _do_cleanup() -> None:
    """删除 system_logs 和 ai_call_logs 中超过 20 天的记录"""
    cutoff = (datetime.now() - timedelta(days=_RETENTION_DAYS)).strftime("%Y-%m-%d %H:%M:%S")
    db = SessionLocal()
    try:
        # 系统日志
        r1 = db.execute(text("DELETE FROM system_logs WHERE timestamp < :cutoff"), {"cutoff": cutoff})
        deleted_sys = r1.rowcount
        # AI 调用日志
        r2 = db.execute(text("DELETE FROM ai_call_logs WHERE called_at < :cutoff"), {"cutoff": cutoff})
        deleted_ai = r2.rowcount
        db.commit()
        if deleted_sys or deleted_ai:
            logger.info("[LogCleanup] 已清理 system_logs %d 条, ai_call_logs %d 条 (截止 %s)",
                        deleted_sys, deleted_ai, cutoff)
    except Exception:
        try:
            db.rollback()
        except Exception:
            pass
        logger.exception("[LogCleanup] 日志清理失败")
    finally:
        db.close()


def _schedule_next() -> None:
    """调度下一次清理"""
    global _timer
    _timer = threading.Timer(_INTERVAL_HOURS * 3600, _run_and_reschedule)
    _timer.daemon = True
    _timer.start()


def _run_and_reschedule() -> None:
    _do_cleanup()
    _schedule_next()


def start_log_cleanup() -> None:
    """启动定时日志清理（首次延迟 60 秒后执行）"""
    global _timer
    _timer = threading.Timer(60, _run_and_reschedule)
    _timer.daemon = True
    _timer.start()
    logger.info("[LogCleanup] 日志清理已启动，保留 %d 天，每 %d 小时执行", _RETENTION_DAYS, _INTERVAL_HOURS)


def stop_log_cleanup() -> None:
    global _timer
    if _timer:
        _timer.cancel()
        _timer = None
