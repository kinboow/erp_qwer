"""
系统动态服务
记录 ERP 同步失败等系统级事件（含详细错误信息）。
用于首页系统动态展示和系统动态独立页面。
"""

import threading
from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database import SessionLocal


_DDL = """
CREATE TABLE IF NOT EXISTS system_activities (
    id          BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    type        VARCHAR(50)  NOT NULL DEFAULT 'info'      COMMENT '类型: info / warning / error / success',
    title       VARCHAR(255) NOT NULL DEFAULT ''           COMMENT '标题',
    content     TEXT         NULL                          COMMENT '详细内容（含错误信息）',
    source      VARCHAR(50)  NOT NULL DEFAULT 'system'     COMMENT '来源: erp_sync / system / wechat',
    created_at  DATETIME     DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_type       (type),
    INDEX idx_source     (source),
    INDEX idx_created_at (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
"""


def ensure_table(db: Session) -> None:
    db.execute(text(_DDL))
    db.commit()


# ---------------------------------------------------------------------------
# 写入
# ---------------------------------------------------------------------------

def create_activity(
    db: Session,
    *,
    title: str,
    content: str = "",
    type: str = "info",
    source: str = "system",
) -> int:
    ensure_table(db)
    result = db.execute(text(
        "INSERT INTO system_activities (type, title, content, source) "
        "VALUES (:type, :title, :content, :source)"
    ), {"type": type, "title": title, "content": content, "source": source})
    db.commit()
    return result.lastrowid


def create_activity_background(
    *,
    title: str,
    content: str = "",
    type: str = "info",
    source: str = "system",
) -> None:
    """在后台线程中写入系统动态，不阻塞调用方"""
    def _run():
        db = SessionLocal()
        try:
            create_activity(db, title=title, content=content, type=type, source=source)
        except Exception:
            pass
        finally:
            db.close()
    threading.Thread(target=_run, daemon=True).start()


# ---------------------------------------------------------------------------
# 查询
# ---------------------------------------------------------------------------

def list_activities(
    db: Session,
    *,
    type: Optional[str] = None,
    source: Optional[str] = None,
    keyword: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
) -> dict[str, Any]:
    ensure_table(db)

    where_clauses = []
    params: dict[str, Any] = {}

    if type:
        where_clauses.append("type = :type")
        params["type"] = type
    if source:
        where_clauses.append("source = :source")
        params["source"] = source
    if keyword:
        where_clauses.append("(title LIKE :kw OR content LIKE :kw)")
        params["kw"] = f"%{keyword}%"

    where_sql = (" WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

    count = db.execute(
        text(f"SELECT COUNT(*) AS cnt FROM system_activities{where_sql}"), params
    ).scalar() or 0

    offset = (page - 1) * page_size
    rows = db.execute(
        text(f"SELECT * FROM system_activities{where_sql} ORDER BY created_at DESC LIMIT :limit OFFSET :offset"),
        {**params, "limit": page_size, "offset": offset},
    ).mappings().all()

    return {
        "total": count,
        "page": page,
        "page_size": page_size,
        "items": [dict(r) for r in rows],
    }


def get_recent_activities(db: Session, limit: int = 10) -> list[dict[str, Any]]:
    """获取最近 N 条系统动态，用于首页展示"""
    ensure_table(db)
    rows = db.execute(
        text("SELECT * FROM system_activities ORDER BY created_at DESC LIMIT :limit"),
        {"limit": limit},
    ).mappings().all()
    return [dict(r) for r in rows]
