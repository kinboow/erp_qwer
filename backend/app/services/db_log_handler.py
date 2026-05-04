"""
自定义 logging Handler —— 将 Python 日志写入 system_logs 表。
仅记录 INFO 及以上级别。
使用后台线程 + 队列批量写入，不阻塞 asyncio 事件循环。
"""

import logging
import queue
import threading
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
    """将日志记录写入 MySQL system_logs 表的 Handler。

    使用后台守护线程 + 队列，emit() 只做入队操作（微秒级），
    实际 DB 写入在独立线程中批量完成，不阻塞主线程和 asyncio 事件循环。
    """

    _BATCH_SIZE = 50         # 每批最多写入条数
    _FLUSH_INTERVAL = 2.0    # 队列等待超时秒数

    def __init__(self, session_factory, level=logging.INFO):
        super().__init__(level)
        self._session_factory = session_factory
        self._queue: queue.Queue = queue.Queue(maxsize=5000)
        self._table_ensured = False
        # 启动后台写入线程
        self._worker = threading.Thread(
            target=self._write_loop, daemon=True, name="db-log-writer",
        )
        self._worker.start()

    def emit(self, record: logging.LogRecord):
        # 防止递归：数据库操作自身也会产生日志
        if getattr(record, '_db_log_skip', False):
            return
        _skip_prefixes = ('sqlalchemy', 'urllib3', 'httpcore', 'httpx', 'uvicorn.access', 'watchfiles', 'asyncio')
        if any(record.name.startswith(p) for p in _skip_prefixes):
            return
        # ERP 同步成功日志只记入系统消息，不写入系统日志；仅保留 WARNING 及以上
        if record.name.startswith('app.services.erp_sync') and record.levelno < logging.WARNING:
            return
        # 健康检查轮询日志只保留 WARNING 及以上，过滤掉高频 INFO
        _health_modules = ('app.services.wechat_health', 'app.services.erp_health')
        if any(record.name.startswith(m) for m in _health_modules) and record.levelno < logging.WARNING:
            return

        try:
            msg = self.format(record)
            entry = {
                "ts": datetime.now(),
                "level": record.levelname.lower(),
                "service": (record.name or '')[:200],
                "msg": msg[:10000],
            }
            # 非阻塞入队；队列满时丢弃，避免背压
            self._queue.put_nowait(entry)
        except queue.Full:
            pass
        except Exception:
            pass

    def _write_loop(self):
        """后台线程：从队列取出日志条目，批量写入数据库。"""
        while True:
            batch: list[dict] = []
            try:
                # 阻塞等待第一条
                item = self._queue.get(timeout=self._FLUSH_INTERVAL)
                batch.append(item)
            except queue.Empty:
                continue

            # 尽量多取，凑成一批
            while len(batch) < self._BATCH_SIZE:
                try:
                    batch.append(self._queue.get_nowait())
                except queue.Empty:
                    break

            self._flush_batch(batch)

    def _flush_batch(self, batch: list[dict]):
        """将一批日志条目写入数据库。"""
        if not batch:
            return
        db = self._session_factory()
        try:
            if not self._table_ensured:
                ensure_system_logs_table(db)
                self._table_ensured = True

            for entry in batch:
                db.execute(text(
                    "INSERT INTO system_logs (timestamp, level, service, message) "
                    "VALUES (:ts, :level, :service, :msg)"
                ), entry)
            db.commit()
            try:
                from app.services.ws_notify import broadcast_sync
                broadcast_sync("new_system_log")
            except Exception:
                pass
        except Exception:
            try:
                db.rollback()
            except Exception:
                pass
        finally:
            db.close()
