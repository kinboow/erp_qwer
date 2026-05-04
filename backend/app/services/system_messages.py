"""
系统消息服务
用于 ERP 同步失败等系统级通知的存储与查询。
与消息日志（message_logs）分离，消息日志仅存储企业微信推送消息。
"""

import json
import threading
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database import SessionLocal


def _fmt_row(row) -> dict:
    item = dict(row)
    for k, v in item.items():
        if isinstance(v, datetime):
            item[k] = v.strftime("%Y-%m-%d %H:%M:%S")
    return item


_DDL = """
CREATE TABLE IF NOT EXISTS system_messages (
    id          BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    level       VARCHAR(20)  NOT NULL DEFAULT 'info'   COMMENT '级别: info / warning / error',
    title       VARCHAR(255) NOT NULL DEFAULT ''        COMMENT '标题',
    content     TEXT         NULL                       COMMENT '详细内容',
    source      VARCHAR(50)  NOT NULL DEFAULT 'system'  COMMENT '来源: erp_sync / system / wechat',
    is_read     TINYINT      NOT NULL DEFAULT 0         COMMENT '是否已读: 0-未读 1-已读',
    created_at  DATETIME     DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_level      (level),
    INDEX idx_source     (source),
    INDEX idx_is_read    (is_read),
    INDEX idx_created_at (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
"""


_sys_msg_table_ensured = False


def ensure_table(db: Session) -> None:
    global _sys_msg_table_ensured
    if _sys_msg_table_ensured:
        return
    db.execute(text(_DDL))
    db.commit()
    _sys_msg_table_ensured = True


# ---------------------------------------------------------------------------
# 写入
# ---------------------------------------------------------------------------

def create_system_message(
    db: Session,
    *,
    title: str,
    content: str = "",
    level: str = "info",
    source: str = "system",
) -> int:
    ensure_table(db)
    result = db.execute(text(
        "INSERT INTO system_messages (level, title, content, source) "
        "VALUES (:level, :title, :content, :source)"
    ), {"level": level, "title": title, "content": content, "source": source})
    db.commit()
    return result.lastrowid


def create_system_message_background(
    *,
    title: str,
    content: str = "",
    level: str = "info",
    source: str = "system",
) -> None:
    """在后台线程中写入系统消息，不阻塞调用方"""
    def _run():
        db = SessionLocal()
        try:
            create_system_message(db, title=title, content=content, level=level, source=source)
        except Exception:
            pass
        finally:
            db.close()
    threading.Thread(target=_run, daemon=True).start()


# ---------------------------------------------------------------------------
# 查询
# ---------------------------------------------------------------------------

def list_system_messages(
    db: Session,
    *,
    level: Optional[str] = None,
    source: Optional[str] = None,
    is_read: Optional[int] = None,
    keyword: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
) -> dict[str, Any]:
    ensure_table(db)

    where_clauses = []
    params: dict[str, Any] = {}

    if level:
        where_clauses.append("level = :level")
        params["level"] = level
    if source:
        where_clauses.append("source = :source")
        params["source"] = source
    if is_read is not None:
        where_clauses.append("is_read = :is_read")
        params["is_read"] = is_read
    if keyword:
        where_clauses.append("(title LIKE :kw OR content LIKE :kw)")
        params["kw"] = f"%{keyword}%"

    where_sql = (" WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

    count = db.execute(
        text(f"SELECT COUNT(*) AS cnt FROM system_messages{where_sql}"), params
    ).scalar() or 0

    offset = (page - 1) * page_size
    rows = db.execute(
        text(f"SELECT * FROM system_messages{where_sql} ORDER BY created_at DESC LIMIT :limit OFFSET :offset"),
        {**params, "limit": page_size, "offset": offset},
    ).mappings().all()

    return {
        "total": count,
        "page": page,
        "page_size": page_size,
        "items": [_fmt_row(r) for r in rows],
    }


def get_unread_count(db: Session) -> int:
    ensure_table(db)
    return db.execute(
        text("SELECT COUNT(*) FROM system_messages WHERE is_read = 0")
    ).scalar() or 0


# ---------------------------------------------------------------------------
# 标记已读
# ---------------------------------------------------------------------------

def mark_as_read(db: Session, message_id: int) -> bool:
    ensure_table(db)
    result = db.execute(
        text("UPDATE system_messages SET is_read = 1 WHERE id = :id AND is_read = 0"),
        {"id": message_id},
    )
    db.commit()
    return result.rowcount > 0


def mark_all_as_read(db: Session) -> int:
    ensure_table(db)
    result = db.execute(text("UPDATE system_messages SET is_read = 1 WHERE is_read = 0"))
    db.commit()
    return result.rowcount
