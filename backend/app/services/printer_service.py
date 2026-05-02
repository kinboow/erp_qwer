"""
打印机服务 — 打印任务队列 + 配置管理（打印由独立客户端完成）
"""
from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# DDL
# ---------------------------------------------------------------------------
_DDL_PRINTER_CONFIG = """
CREATE TABLE IF NOT EXISTS printer_config (
    id          BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    config_key  VARCHAR(100) NOT NULL,
    config_value TEXT NOT NULL DEFAULT '',
    updated_at  DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_key (config_key)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
"""

_DDL_PRINT_QUEUE = """
CREATE TABLE IF NOT EXISTS print_queue (
    id          BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    order_no    VARCHAR(100) NOT NULL,
    doc_type    VARCHAR(50)  NOT NULL DEFAULT 'picking' COMMENT 'picking=配货单',
    pdf_object  VARCHAR(500) NOT NULL DEFAULT '' COMMENT 'OSS object name',
    status      VARCHAR(20)  NOT NULL DEFAULT 'pending' COMMENT 'pending/printing/done/failed',
    attempts    INT UNSIGNED NOT NULL DEFAULT 0,
    error_msg   VARCHAR(500) NOT NULL DEFAULT '',
    created_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at  DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_status (status),
    INDEX idx_created (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
"""


def ensure_printer_tables(db: Session) -> None:
    db.execute(text(_DDL_PRINTER_CONFIG))
    db.execute(text(_DDL_PRINT_QUEUE))
    db.commit()


# ---------------------------------------------------------------------------
# 配置读写
# ---------------------------------------------------------------------------
def get_printer_config(db: Session) -> dict[str, str]:
    ensure_printer_tables(db)
    rows = db.execute(text("SELECT config_key, config_value FROM printer_config")).mappings().all()
    return {r["config_key"]: r["config_value"] for r in rows}


def save_printer_config(db: Session, data: dict[str, Any]) -> dict[str, str]:
    ensure_printer_tables(db)
    for key, value in data.items():
        if not key.startswith("printer_"):
            continue
        db.execute(
            text(
                "INSERT INTO printer_config (config_key, config_value) VALUES (:key, :val) "
                "ON DUPLICATE KEY UPDATE config_value = VALUES(config_value)"
            ),
            {"key": key, "val": str(value)},
        )
    db.commit()
    return get_printer_config(db)


# ---------------------------------------------------------------------------
# 打印队列操作
# ---------------------------------------------------------------------------
def enqueue_print_job(db: Session, order_no: str, doc_type: str = "picking") -> dict[str, Any]:
    """将打印任务加入队列，由打印客户端轮询取走"""
    ensure_printer_tables(db)
    # 生成 PDF
    if doc_type == "picking":
        from app.services.picking_print import generate_picking_pdf
        generate_picking_pdf(db, order_no)
        pdf_object = f"picking/{order_no}.pdf"
    else:
        raise ValueError(f"不支持的文档类型: {doc_type}")

    db.execute(
        text(
            "INSERT INTO print_queue (order_no, doc_type, pdf_object, status) "
            "VALUES (:no, :dt, :obj, 'pending')"
        ),
        {"no": order_no, "dt": doc_type, "obj": pdf_object},
    )
    db.commit()
    logger.info("打印任务已入队: order=%s doc_type=%s", order_no, doc_type)
    return {"queued": True, "order_no": order_no, "doc_type": doc_type}


def poll_print_jobs(db: Session, limit: int = 10) -> list[dict[str, Any]]:
    """获取待打印任务（pending 或 failed 且重试<3次）"""
    ensure_printer_tables(db)
    rows = db.execute(
        text(
            "SELECT id, order_no, doc_type, pdf_object, status, attempts, error_msg, created_at "
            "FROM print_queue "
            "WHERE status IN ('pending', 'failed') AND attempts < 3 "
            "ORDER BY created_at ASC LIMIT :lim"
        ),
        {"lim": limit},
    ).mappings().all()
    return [dict(r) for r in rows]


def ack_print_job(db: Session, job_id: int, success: bool, error: str = "") -> None:
    """客户端回报打印结果"""
    ensure_printer_tables(db)
    if success:
        db.execute(
            text("UPDATE print_queue SET status = 'done', attempts = attempts + 1, updated_at = NOW() WHERE id = :id"),
            {"id": job_id},
        )
    else:
        db.execute(
            text(
                "UPDATE print_queue SET status = IF(attempts + 1 >= 3, 'failed', 'failed'), "
                "attempts = attempts + 1, error_msg = :err, updated_at = NOW() WHERE id = :id"
            ),
            {"id": job_id, "err": error[:500]},
        )
    db.commit()


# ---------------------------------------------------------------------------
# 审核下单后自动入队
# ---------------------------------------------------------------------------
def auto_print_picking_list(db: Session, order_no: str) -> dict[str, Any] | None:
    """审核下单后将配货单打印任务加入队列"""
    cfg = get_printer_config(db)
    if cfg.get("printer_auto_print") != "true":
        logger.info("自动打印未启用，跳过 order=%s", order_no)
        return None

    try:
        result = enqueue_print_job(db, order_no, doc_type="picking")
        return {"printed": True, "message": "配货单已加入打印队列，等待打印客户端处理"}
    except Exception as exc:
        logger.error("配货单入队失败: order=%s error=%s", order_no, exc)
        return {"printed": False, "error": str(exc)}
