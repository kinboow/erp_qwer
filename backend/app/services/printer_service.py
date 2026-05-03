"""
打印机服务 — 打印任务队列 + 配置管理 + 客户端心跳（打印由独立客户端完成）
"""
from __future__ import annotations

import logging
import time
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 客户端心跳（内存级，重启归零）
# ---------------------------------------------------------------------------
_CLIENT_TTL_SECONDS = 30
_client_heartbeats: dict[str, dict[str, Any]] = {}


def update_client_heartbeat(hostname: str, printer_name: str = "", printers: list[str] | None = None) -> None:
    if not hostname:
        return
    _client_heartbeats[hostname] = {
        "hostname": hostname,
        "printer_name": printer_name or "",
        "printers": printers or [],
        "last_seen": time.time(),
    }


def list_client_statuses() -> list[dict[str, Any]]:
    now = time.time()
    rows: list[dict[str, Any]] = []
    for host, item in _client_heartbeats.items():
        last_seen = float(item.get("last_seen") or 0)
        elapsed = now - last_seen if last_seen else 999999
        rows.append(
            {
                "hostname": host,
                "printer_name": item.get("printer_name", ""),
                "printers": item.get("printers", []) or [],
                "last_seen": last_seen if last_seen else None,
                "seconds_ago": round(elapsed, 1),
                "online": elapsed < _CLIENT_TTL_SECONDS,
            }
        )
    rows.sort(key=lambda x: (0 if x["online"] else 1, x["hostname"]))
    return rows


def get_client_status() -> dict[str, Any]:
    rows = list_client_statuses()
    if not rows:
        return {"online": False, "hostname": "", "printer_name": "", "last_seen": None, "seconds_ago": None}
    return rows[0]

# ---------------------------------------------------------------------------
# DDL
# ---------------------------------------------------------------------------
_DDL_PRINTER_CONFIG = """
CREATE TABLE IF NOT EXISTS printer_config (
    id          BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    config_key  VARCHAR(100) NOT NULL,
    config_value TEXT NOT NULL,
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
    target_client VARCHAR(255) NOT NULL DEFAULT '' COMMENT '目标客户端主机名，空=任意客户端',
    target_printer VARCHAR(255) NOT NULL DEFAULT '' COMMENT '目标打印机，空=客户端当前选择',
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
    try:
        cols = {r["Field"] for r in db.execute(text("SHOW COLUMNS FROM print_queue")).mappings().all()}
        if "target_client" not in cols:
            db.execute(text("ALTER TABLE print_queue ADD COLUMN target_client VARCHAR(255) NOT NULL DEFAULT ''"))
        if "target_printer" not in cols:
            db.execute(text("ALTER TABLE print_queue ADD COLUMN target_printer VARCHAR(255) NOT NULL DEFAULT ''"))
    except Exception:
        logger.warning("print_queue 表结构兼容升级失败，跳过", exc_info=True)
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

    cfg = get_printer_config(db)
    target_client = cfg.get("printer_target_client", "")
    target_printer = cfg.get("printer_target_printer", "")

    db.execute(
        text(
            "INSERT INTO print_queue (order_no, doc_type, pdf_object, target_client, target_printer, status) "
            "VALUES (:no, :dt, :obj, :tc, :tp, 'pending')"
        ),
        {"no": order_no, "dt": doc_type, "obj": pdf_object, "tc": target_client, "tp": target_printer},
    )
    db.commit()
    logger.info("打印任务已入队: order=%s doc_type=%s", order_no, doc_type)
    return {"queued": True, "order_no": order_no, "doc_type": doc_type}


def enqueue_test_print_job(db: Session, target_client: str, target_printer: str) -> dict[str, Any]:
    """入队一个测试打印任务"""
    ensure_printer_tables(db)
    test_order_no = f"TEST-{int(time.time())}"
    db.execute(
        text(
            "INSERT INTO print_queue (order_no, doc_type, pdf_object, target_client, target_printer, status) "
            "VALUES (:no, 'test', '', :tc, :tp, 'pending')"
        ),
        {"no": test_order_no, "tc": target_client or "", "tp": target_printer or ""},
    )
    db.commit()
    return {"queued": True, "order_no": test_order_no, "doc_type": "test"}


def poll_print_jobs(db: Session, hostname: str = "", limit: int = 10) -> list[dict[str, Any]]:
    """获取待打印任务（pending 或 failed 且重试<3次）"""
    ensure_printer_tables(db)
    rows = db.execute(
        text(
            "SELECT id, order_no, doc_type, pdf_object, target_client, target_printer, status, attempts, error_msg, created_at "
            "FROM print_queue "
            "WHERE status IN ('pending', 'failed') AND attempts < 3 "
            "  AND (target_client = '' OR target_client = :host) "
            "ORDER BY created_at ASC LIMIT :lim"
        ),
        {"lim": limit, "host": hostname or ""},
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
