"""
自定义 logging Handler —— 将 Python 日志写入 system_logs 表。
仅记录 INFO 及以上级别。
"""

import logging
import threading
import traceback
from datetime import datetime

from sqlalchemy import text


_DDL_DONE = False
_DDL_LOCK = threading.Lock()


def ensure_system_logs_table(db):
    """确保 system_logs 表存在"""
    global _DDL_DONE
    if _DDL_DONE:
        return
    with _DDL_LOCK:
        if _DDL_DONE:
            return
        try:
            db.execute(text(
                "CREATE TABLE IF NOT EXISTS system_logs ("
                "id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY, "
                "timestamp DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, "
                "level VARCHAR(20) NOT NULL DEFAULT 'info', "
                "service VARCHAR(200) DEFAULT '', "
                "message TEXT NOT NULL, "
                "INDEX idx_timestamp (timestamp), "
                "INDEX idx_level (level)"
                ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4"
            ))
            db.commit()
            _DDL_DONE = True
        except Exception:
            try:
                db.rollback()
            except Exception:
                pass


class DatabaseLogHandler(logging.Handler):
    """将日志记录写入 MySQL system_logs 表的 Handler"""

    def __init__(self, session_factory, level=logging.INFO):
        super().__init__(level)
        self._session_factory = session_factory
        self._table_ensured = False

    def emit(self, record: logging.LogRecord):
        # 防止递归：数据库操作自身也会产生日志
        if getattr(record, '_db_log_skip', False):
            return
        if record.name.startswith('sqlalchemy') or record.name.startswith('urllib3') or record.name.startswith('httpcore'):
            return

        try:
            msg = self.format(record)
            level = record.levelname.lower()
            service = record.name or ''
            now = datetime.utcnow()

            db = self._session_factory()
            try:
                # 标记本次 session 的日志操作，避免递归
                record._db_log_skip = True
                if not self._table_ensured:
                    ensure_system_logs_table(db)
                    self._table_ensured = True

                db.execute(text(
                    "INSERT INTO system_logs (timestamp, level, service, message) "
                    "VALUES (:ts, :level, :service, :msg)"
                ), {
                    "ts": now,
                    "level": level,
                    "service": service[:200],
                    "msg": msg[:10000],
                })
                db.commit()
            except Exception:
                try:
                    db.rollback()
                except Exception:
                    pass
            finally:
                db.close()
        except Exception:
            # 绝不能让日志 handler 崩溃影响主程序
            pass
