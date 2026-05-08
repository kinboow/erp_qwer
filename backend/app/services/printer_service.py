"""
打印机服务 — 打印任务队列 + 配置管理 + 客户端心跳（打印由独立客户端完成）
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database import SessionLocal, run_in_threadpool

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


def get_client_status_by_hostname(hostname: str) -> dict[str, Any]:
    """查询指定 hostname 的心跳状态。"""
    if not hostname:
        return {"online": False, "hostname": "", "printer_name": "", "last_seen": None, "seconds_ago": None}
    item = _client_heartbeats.get(hostname)
    if not item:
        return {"online": False, "hostname": hostname, "printer_name": "", "last_seen": None, "seconds_ago": None}
    now = time.time()
    last_seen = float(item.get("last_seen") or 0)
    elapsed = now - last_seen if last_seen else 999999
    return {
        "hostname": hostname,
        "printer_name": item.get("printer_name", ""),
        "printers": item.get("printers", []) or [],
        "last_seen": last_seen if last_seen else None,
        "seconds_ago": round(elapsed, 1),
        "online": elapsed < _CLIENT_TTL_SECONDS,
    }

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

_DDL_SCHEDULE_TASK_LOGS = """
CREATE TABLE IF NOT EXISTS scheduled_task_logs (
    id            BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    task_key      VARCHAR(100) NOT NULL,
    run_date      VARCHAR(20) NOT NULL DEFAULT '',
    target_date   VARCHAR(20) NOT NULL DEFAULT '',
    trigger_type  VARCHAR(50) NOT NULL DEFAULT '',
    status        VARCHAR(20) NOT NULL DEFAULT 'running',
    summary       VARCHAR(500) NOT NULL DEFAULT '',
    result_json   LONGTEXT NULL,
    log_text      LONGTEXT NULL,
    created_at    DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at    DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_task_created (task_key, created_at),
    INDEX idx_run_date (run_date)
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


_printer_tables_ensured = False
_scheduled_unshipped_task: asyncio.Task | None = None
_scheduled_unshipped_running = False


def ensure_printer_tables(db: Session) -> None:
    global _printer_tables_ensured
    if _printer_tables_ensured:
        return
    db.execute(text(_DDL_PRINTER_CONFIG))
    db.execute(text(_DDL_PRINT_QUEUE))
    db.execute(text(_DDL_SCHEDULE_TASK_LOGS))
    try:
        cols = {r["Field"] for r in db.execute(text("SHOW COLUMNS FROM print_queue")).mappings().all()}
        if "target_client" not in cols:
            db.execute(text("ALTER TABLE print_queue ADD COLUMN target_client VARCHAR(255) NOT NULL DEFAULT ''"))
        if "target_printer" not in cols:
            db.execute(text("ALTER TABLE print_queue ADD COLUMN target_printer VARCHAR(255) NOT NULL DEFAULT ''"))
    except Exception:
        logger.warning("print_queue 表结构兼容升级失败，跳过", exc_info=True)
    db.commit()
    _printer_tables_ensured = True


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
    if "printer_unshipped_schedule_enabled" in data or "printer_unshipped_schedule_time" in data:
        effective_date = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
        db.execute(
            text(
                "INSERT INTO printer_config (config_key, config_value) VALUES ('printer_unshipped_schedule_effective_date', :val) "
                "ON DUPLICATE KEY UPDATE config_value = VALUES(config_value)"
            ),
            {"val": effective_date},
        )
    db.commit()
    return get_printer_config(db)


def _extract_object_name_from_oss_url(oss_url: str) -> str:
    value = str(oss_url or "").strip()
    if "/oss-file/" not in value:
        return ""
    return value.split("/oss-file/")[-1].split("?")[0]


def _save_printer_config_value(db: Session, key: str, value: Any) -> None:
    db.execute(
        text(
            "INSERT INTO printer_config (config_key, config_value) VALUES (:key, :val) "
            "ON DUPLICATE KEY UPDATE config_value = VALUES(config_value)"
        ),
        {"key": key, "val": str(value)},
    )


def _insert_scheduled_task_log(
    db: Session,
    task_key: str,
    run_date: str,
    target_date: str,
    trigger_type: str,
    status: str,
    summary: str,
    log_text: str,
    result_json: str,
) -> int:
    result = db.execute(
        text(
            "INSERT INTO scheduled_task_logs "
            "(task_key, run_date, target_date, trigger_type, status, summary, result_json, log_text) "
            "VALUES (:task_key, :run_date, :target_date, :trigger_type, :status, :summary, :result_json, :log_text)"
        ),
        {
            "task_key": task_key,
            "run_date": run_date,
            "target_date": target_date,
            "trigger_type": trigger_type,
            "status": status,
            "summary": summary[:500],
            "result_json": result_json,
            "log_text": log_text,
        },
    )
    db.commit()
    return int(result.lastrowid or 0)


def _update_scheduled_task_log(
    db: Session,
    log_id: int,
    *,
    status: str,
    summary: str,
    log_text: str,
    result_json: str,
) -> None:
    db.execute(
        text(
            "UPDATE scheduled_task_logs "
            "SET status = :status, summary = :summary, log_text = :log_text, result_json = :result_json, updated_at = NOW() "
            "WHERE id = :id"
        ),
        {
            "id": log_id,
            "status": status,
            "summary": summary[:500],
            "log_text": log_text,
            "result_json": result_json,
        },
    )
    db.commit()


def _append_schedule_log(lines: list[str], message: str) -> None:
    lines.append(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {message}")


def _sync_unshipped_report_before_print(log_lines: list[str]) -> dict[str, Any]:
    from app.services.erp_bridge import _erp_client
    from app.services.erp_sync import _sync_module, is_module_syncing, sync_unshipped_report

    if _erp_client is None:
        raise ValueError("ERP 客户端未初始化，无法在打印前同步未发货报表")

    sync_days_back = 30
    wait_seconds = 0
    wait_timeout_seconds = 600
    wait_step_seconds = 2
    waiting_logged = False

    while True:
        if is_module_syncing("unshipped"):
            if not waiting_logged:
                _append_schedule_log(log_lines, "检测到未发货报表正在同步，等待当前同步完成后再执行打印前预同步")
                waiting_logged = True
            time.sleep(wait_step_seconds)
            wait_seconds += wait_step_seconds
            if wait_seconds >= wait_timeout_seconds:
                raise TimeoutError("等待未发货报表同步完成超时，无法继续执行打印任务")
            continue

        _append_schedule_log(log_lines, f"开始打印前预同步未发货报表（窗口天数={sync_days_back}）")
        started_at = time.time()
        sync_result = asyncio.run(
            _sync_module(
                "unshipped",
                sync_unshipped_report(_erp_client, days_back=sync_days_back),
                trigger="scheduled_preprint",
            )
        )
        if sync_result is None:
            if not waiting_logged:
                _append_schedule_log(log_lines, "打印前预同步遇到并发同步占用，等待对方完成后重试")
                waiting_logged = True
            time.sleep(wait_step_seconds)
            wait_seconds += wait_step_seconds
            if wait_seconds >= wait_timeout_seconds:
                raise TimeoutError("未发货报表预同步并发等待超时，无法继续执行打印任务")
            continue

        elapsed = round(time.time() - started_at, 2)
        _append_schedule_log(
            log_lines,
            "打印前预同步完成："
            f"发现 {sync_result.get('total_found', 0)} 条，"
            f"成功 {sync_result.get('synced', 0)} 条，"
            f"失败 {sync_result.get('failed', 0)} 条，耗时 {elapsed}s",
        )
        return sync_result


def _json_text(data: Any) -> str:
    try:
        return json.dumps(data, ensure_ascii=False)
    except Exception:
        return "{}"


def _validate_remote_schedule_target(cfg: dict[str, Any]) -> tuple[str, str]:
    target_client = str(cfg.get("printer_target_client") or "").strip()
    target_printer = str(cfg.get("printer_target_printer") or "").strip()
    if not target_client:
        raise ValueError("未配置远程打印客户端，请先到远程打印机里选择客户端")
    return target_client, target_printer


def list_scheduled_task_logs(db: Session, task_key: str = "unshipped_daily", limit: int = 50) -> list[dict[str, Any]]:
    ensure_printer_tables(db)
    limit_value = max(1, min(int(limit or 50), 200))
    if task_key:
        rows = db.execute(
            text(
                "SELECT id, task_key, run_date, target_date, trigger_type, status, summary, result_json, log_text, created_at, updated_at "
                "FROM scheduled_task_logs WHERE task_key = :task_key ORDER BY created_at DESC, id DESC LIMIT :limit"
            ),
            {"task_key": task_key, "limit": limit_value},
        ).mappings().all()
    else:
        rows = db.execute(
            text(
                "SELECT id, task_key, run_date, target_date, trigger_type, status, summary, result_json, log_text, created_at, updated_at "
                "FROM scheduled_task_logs ORDER BY created_at DESC, id DESC LIMIT :limit"
            ),
            {"limit": limit_value},
        ).mappings().all()
    result: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        raw = item.get("result_json") or ""
        try:
            item["result"] = json.loads(raw) if raw else {}
        except Exception:
            item["result"] = {}
        result.append(item)
    return result


def _is_true(value: Any) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _is_valid_schedule_time(value: str) -> bool:
    try:
        datetime.strptime(str(value or "").strip(), "%H:%M")
        return True
    except Exception:
        return False


def _is_schedule_effective_today(cfg: dict[str, Any], today: str) -> bool:
    effective_date = str(cfg.get("printer_unshipped_schedule_effective_date") or "").strip()
    if not effective_date:
        return True
    return today >= effective_date


def queue_yesterday_unshipped_orders_for_print(db: Session, target_date: str) -> dict[str, Any]:
    """将指定日期下单且当前仍未发货的订单，按订单维度生成待发货单并入打印队列。"""
    ensure_printer_tables(db)
    from app.services.erp_sync import ensure_tables as ensure_erp_tables
    ensure_erp_tables(db)

    rows = db.execute(
        text(
            "SELECT u.id, u.order_no, "
            "COALESCE(NULLIF(o.customer_name,''), NULLIF(c.customer_name,''), u.customer_id) AS customer_name "
            "FROM erp_unshipped_report u "
            "LEFT JOIN erp_sales_orders o ON u.order_no = o.order_no "
            "LEFT JOIN downstream_customers c ON u.customer_id = c.erp_customer_id "
            "WHERE LEFT(u.order_date, 10) <= :target_date "
            "  AND COALESCE(u.unshipped_qty, 0) > 0 "
            "ORDER BY u.order_no ASC, u.product_no ASC, u.id ASC"
        ),
        {"target_date": target_date},
    ).mappings().all()

    if not rows:
        logger.info("[定时任务] %s 无符合条件的截至昨日仍未发货订单", target_date)
        return {"target_date": target_date, "order_count": 0, "queued_count": 0, "orders": []}

    from collections import OrderedDict
    from app.services.unshipped_print import generate_unshipped_pdf

    order_groups: OrderedDict[str, dict[str, Any]] = OrderedDict()
    for row in rows:
        order_no = str(row.get("order_no") or "").strip()
        if not order_no:
            continue
        if order_no not in order_groups:
            order_groups[order_no] = {
                "ids": [],
                "customer_name": str(row.get("customer_name") or "").strip(),
            }
        order_groups[order_no]["ids"].append(int(row["id"]))
        if not order_groups[order_no]["customer_name"]:
            order_groups[order_no]["customer_name"] = str(row.get("customer_name") or "").strip()

    queued_orders: list[str] = []
    for order_no, meta in order_groups.items():
        result = generate_unshipped_pdf(db, meta["ids"], meta.get("customer_name") or "")
        pdf_object = str(result.get("object_name") or "").strip() or _extract_object_name_from_oss_url(result.get("oss_url") or "")
        if not pdf_object:
            raise ValueError(f"订单 {order_no} 生成待发货单后未得到 PDF 对象路径")
        enqueue_existing_pdf(db, order_no, doc_type="unshipped", pdf_object=pdf_object)
        queued_orders.append(order_no)

    logger.info("[定时任务] %s 截至昨日仍未发货订单已入打印队列: %s", target_date, queued_orders)
    return {
        "target_date": target_date,
        "order_count": len(order_groups),
        "queued_count": len(queued_orders),
        "orders": queued_orders,
    }


def _format_unshipped_sizes(raw_value: Any) -> str:
    try:
        data = json.loads(str(raw_value or "[]"))
    except Exception:
        data = []
    parts: list[str] = []
    for item in data if isinstance(data, list) else []:
        size = str((item or {}).get("size") or "").strip()
        qty = (item or {}).get("qty")
        if not size:
            continue
        try:
            qty_text = str(int(float(qty)))
        except Exception:
            qty_text = str(qty or "")
        parts.append(f"{size}×{qty_text}")
    return "、".join(parts)


def _list_customer_room_targets(db: Session, erp_customer_id: str, customer_name: str = "") -> list[dict[str, Any]]:
    from app.services.downstream_support import ensure_downstream_support_tables

    ensure_downstream_support_tables(db)
    erp_customer_id = str(erp_customer_id or "").strip()
    customer_name = str(customer_name or "").strip()
    rows: list[dict[str, Any]] = []
    if erp_customer_id:
        rows = db.execute(
            text(
                "SELECT r.instance_id, r.room_id, COALESCE(r.room_name, '') AS room_name, c.id AS customer_id, COALESCE(c.customer_name, '') AS customer_name "
                "FROM downstream_customers c "
                "INNER JOIN downstream_customer_wechat_rooms r ON r.customer_id = c.id "
                "WHERE c.deleted_at IS NULL AND c.status = 1 AND r.room_type = 'customer' AND c.erp_customer_id = :erp_customer_id "
                "ORDER BY r.id ASC"
            ),
            {"erp_customer_id": erp_customer_id},
        ).mappings().all()
    elif customer_name:
        rows = db.execute(
            text(
                "SELECT r.instance_id, r.room_id, COALESCE(r.room_name, '') AS room_name, c.id AS customer_id, COALESCE(c.customer_name, '') AS customer_name "
                "FROM downstream_customers c "
                "INNER JOIN downstream_customer_wechat_rooms r ON r.customer_id = c.id "
                "WHERE c.deleted_at IS NULL AND c.status = 1 AND r.room_type = 'customer' AND c.customer_name = :customer_name "
                "ORDER BY r.id ASC"
            ),
            {"customer_name": customer_name},
        ).mappings().all()
    return [dict(row) for row in rows]


def _load_unshipped_order_groups(
    db: Session,
    *,
    target_date: str = "",
    order_nos: list[str] | None = None,
) -> dict[str, dict[str, Any]]:
    from collections import OrderedDict

    ensure_printer_tables(db)
    from app.services.erp_sync import ensure_tables as ensure_erp_tables
    ensure_erp_tables(db)

    params: dict[str, Any] = {}
    where_sql = "COALESCE(u.unshipped_qty, 0) > 0"
    if target_date:
        where_sql += " AND LEFT(u.order_date, 10) = :target_date"
        params["target_date"] = target_date
    elif order_nos:
        placeholders = []
        for idx, order_no in enumerate(order_nos):
            key = f"order_no_{idx}"
            placeholders.append(f":{key}")
            params[key] = str(order_no or "").strip()
        if not placeholders:
            return {}
        where_sql += f" AND u.order_no IN ({', '.join(placeholders)})"

    rows = db.execute(
        text(
            "SELECT u.order_no, LEFT(u.order_date, 10) AS order_date, u.product_no, COALESCE(u.product_name, '') AS product_name, COALESCE(u.color, '') AS color, "
            "COALESCE(u.unshipped_qty, 0) AS unshipped_qty, COALESCE(u.unshipped_sizes_json, '[]') AS unshipped_sizes_json, "
            "COALESCE(NULLIF(o.customer_id, ''), u.customer_id, '') AS erp_customer_id, COALESCE(o.customer_name, '') AS customer_name "
            "FROM erp_unshipped_report u "
            "LEFT JOIN erp_sales_orders o ON u.order_no = o.order_no "
            f"WHERE {where_sql} "
            "ORDER BY u.order_no ASC, u.product_no ASC, u.id ASC"
        ),
        params,
    ).mappings().all()

    grouped: OrderedDict[str, dict[str, Any]] = OrderedDict()
    for row in rows:
        order_no = str(row.get("order_no") or "").strip()
        if not order_no:
            continue
        if order_no not in grouped:
            grouped[order_no] = {
                "order_no": order_no,
                "order_date": str(row.get("order_date") or "").strip(),
                "erp_customer_id": str(row.get("erp_customer_id") or "").strip(),
                "customer_name": str(row.get("customer_name") or "").strip(),
                "items": [],
            }
        size_text = _format_unshipped_sizes(row.get("unshipped_sizes_json"))
        try:
            qty_text = str(int(float(row.get("unshipped_qty") or 0)))
        except Exception:
            qty_text = str(row.get("unshipped_qty") or 0)
        item_line = f"{row.get('product_no') or ''} {row.get('product_name') or ''} {row.get('color') or ''}".strip()
        if size_text:
            item_line = f"{item_line}，待发尺码：{size_text}"
        else:
            item_line = f"{item_line}，待发数量：{qty_text}"
        grouped[order_no]["items"].append(item_line)
        if not grouped[order_no]["erp_customer_id"]:
            grouped[order_no]["erp_customer_id"] = str(row.get("erp_customer_id") or "").strip()
        if not grouped[order_no]["customer_name"]:
            grouped[order_no]["customer_name"] = str(row.get("customer_name") or "").strip()
        if not grouped[order_no]["order_date"]:
            grouped[order_no]["order_date"] = str(row.get("order_date") or "").strip()
    return dict(grouped)


def _upsert_customer_order_followup(
    db: Session,
    *,
    order_no: str,
    room_id: str,
    instance_id: int | None,
    customer_id: int | None,
    customer_name: str,
    erp_customer_id: str,
    order_date: str,
    current_stage: str,
    followup_status: str,
    ask_date: str,
    item_lines: list[str],
) -> None:
    from app.services.downstream_support import ensure_downstream_support_tables

    ensure_downstream_support_tables(db)
    db.execute(
        text(
            "INSERT INTO customer_order_followups ("
            "order_no, room_id, instance_id, customer_id, customer_name, erp_customer_id, order_date, current_stage, followup_status, ask_count, last_asked_date, last_decision, next_followup_date, item_summary_json"
            ") VALUES ("
            ":order_no, :room_id, :instance_id, :customer_id, :customer_name, :erp_customer_id, :order_date, :current_stage, :followup_status, 1, :last_asked_date, '', '', :item_summary_json"
            ") ON DUPLICATE KEY UPDATE "
            "instance_id = VALUES(instance_id), customer_id = VALUES(customer_id), customer_name = VALUES(customer_name), erp_customer_id = VALUES(erp_customer_id), "
            "order_date = VALUES(order_date), current_stage = VALUES(current_stage), followup_status = VALUES(followup_status), "
            "ask_count = ask_count + 1, last_asked_date = VALUES(last_asked_date), item_summary_json = VALUES(item_summary_json), updated_at = NOW()"
        ),
        {
            "order_no": order_no,
            "room_id": room_id,
            "instance_id": instance_id,
            "customer_id": customer_id,
            "customer_name": customer_name,
            "erp_customer_id": erp_customer_id,
            "order_date": order_date,
            "current_stage": current_stage,
            "followup_status": followup_status,
            "last_asked_date": ask_date,
            "item_summary_json": _json_text(item_lines),
        },
    )


def get_room_pending_followups(db: Session, room_id: str) -> list[dict[str, Any]]:
    from app.services.downstream_support import ensure_downstream_support_tables

    ensure_downstream_support_tables(db)
    rows = db.execute(
        text(
            "SELECT f.id, f.order_no, f.room_id, f.customer_name, f.current_stage, f.followup_status, f.ask_count, f.last_asked_date, "
            "f.last_decision, f.next_followup_date, f.item_summary_json "
            "FROM customer_order_followups f "
            "WHERE f.room_id = :room_id AND f.followup_status = 'pending_customer' "
            "  AND EXISTS (SELECT 1 FROM erp_unshipped_report u WHERE u.order_no = f.order_no AND COALESCE(u.unshipped_qty, 0) > 0) "
            "ORDER BY f.last_asked_date DESC, f.updated_at DESC, f.id DESC LIMIT 10"
        ),
        {"room_id": room_id},
    ).mappings().all()
    result: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        try:
            item["item_summary"] = json.loads(item.get("item_summary_json") or "[]")
        except Exception:
            item["item_summary"] = []
        item.pop("item_summary_json", None)
        result.append(item)
    return result


def mark_followup_continue_decision(db: Session, room_id: str, order_no: str) -> dict[str, Any]:
    from app.services.downstream_support import ensure_downstream_support_tables

    ensure_downstream_support_tables(db)
    row = db.execute(
        text(
            "SELECT id, order_no, current_stage, followup_status FROM customer_order_followups "
            "WHERE room_id = :room_id AND order_no = :order_no AND followup_status = 'pending_customer' "
            "ORDER BY id DESC LIMIT 1"
        ),
        {"room_id": room_id, "order_no": order_no},
    ).mappings().first()
    if not row:
        raise ValueError(f"当前群未找到订单 {order_no} 的待确认跟进记录")
    next_followup_date = (datetime.now() + timedelta(days=5)).strftime("%Y-%m-%d")
    db.execute(
        text(
            "UPDATE customer_order_followups SET followup_status = 'continued_waiting', current_stage = 'fifth_day', "
            "last_decision = 'continue', last_decision_at = NOW(), next_followup_date = :next_followup_date, updated_at = NOW() "
            "WHERE id = :id"
        ),
        {"id": row["id"], "next_followup_date": next_followup_date},
    )
    db.commit()
    return {
        "ok": True,
        "order_no": order_no,
        "status": "continued_waiting",
        "next_followup_date": next_followup_date,
    }


def mark_followup_cancel_review_created(db: Session, room_id: str, order_no: str, review_id: int) -> None:
    from app.services.downstream_support import ensure_downstream_support_tables

    ensure_downstream_support_tables(db)
    db.execute(
        text(
            "UPDATE customer_order_followups SET followup_status = 'cancel_review_created', current_stage = 'cancel_review', "
            "last_decision = 'cancel', last_decision_at = NOW(), last_review_id = :review_id, updated_at = NOW() "
            "WHERE room_id = :room_id AND order_no = :order_no AND followup_status = 'pending_customer'"
        ),
        {"room_id": room_id, "order_no": order_no, "review_id": review_id},
    )
    db.commit()


def _mark_followup_completed_if_resolved(db: Session, order_nos: list[str]) -> None:
    from app.services.downstream_support import ensure_downstream_support_tables

    ensure_downstream_support_tables(db)
    clean_order_nos = [str(item or "").strip() for item in order_nos if str(item or "").strip()]
    if not clean_order_nos:
        return
    unresolved = set(_load_unshipped_order_groups(db, order_nos=clean_order_nos).keys())
    resolved = [order_no for order_no in clean_order_nos if order_no not in unresolved]
    if not resolved:
        return
    placeholders = []
    params: dict[str, Any] = {}
    for idx, order_no in enumerate(resolved):
        key = f"resolved_{idx}"
        placeholders.append(f":{key}")
        params[key] = order_no
    db.execute(
        text(
            f"UPDATE customer_order_followups SET followup_status = 'completed', updated_at = NOW() WHERE order_no IN ({', '.join(placeholders)}) "
            "AND followup_status IN ('pending_customer', 'continued_waiting', 'cancel_review_created')"
        ),
        params,
    )
    db.commit()


async def _run_third_day_unshipped_notify_once(trigger_type: str = "scheduled", mark_run_date: bool = True) -> dict[str, Any]:
    from app.services.notify_group import send_to_notification_groups
    from app.services.wechat_reply import send_room_at

    db = SessionLocal()
    now = datetime.now()
    run_date = now.strftime("%Y-%m-%d")
    target_date = (now - timedelta(days=2)).strftime("%Y-%m-%d")
    log_lines: list[str] = []
    log_id = 0
    try:
        ensure_printer_tables(db)
        from app.services.erp_sync import ensure_tables as ensure_erp_tables
        from app.services.downstream_support import ensure_downstream_support_tables
        ensure_erp_tables(db)
        ensure_downstream_support_tables(db)

        log_id = _insert_scheduled_task_log(
            db,
            task_key="third_day_unshipped_notify",
            run_date=run_date,
            target_date=target_date,
            trigger_type=trigger_type,
            status="running",
            summary="任务执行中",
            log_text="",
            result_json="{}",
        )
        _append_schedule_log(log_lines, f"开始执行第三天未完全发货通知 trigger={trigger_type}")
        _append_schedule_log(log_lines, f"第三天统计下单日期：{target_date}")

        third_day_groups = _load_unshipped_order_groups(db, target_date=target_date)
        due_followup_rows = db.execute(
            text(
                "SELECT id, order_no, room_id, instance_id, customer_id, customer_name, erp_customer_id, order_date, ask_count "
                "FROM customer_order_followups WHERE followup_status = 'continued_waiting' AND next_followup_date <= :today "
                "ORDER BY next_followup_date ASC, id ASC"
            ),
            {"today": run_date},
        ).mappings().all()
        due_order_nos = sorted({str(row.get("order_no") or "").strip() for row in due_followup_rows if str(row.get("order_no") or "").strip()})
        if due_order_nos:
            _mark_followup_completed_if_resolved(db, due_order_nos)
        fifth_day_groups = _load_unshipped_order_groups(db, order_nos=due_order_nos) if due_order_nos else {}

        if not third_day_groups and not fifth_day_groups:
            _append_schedule_log(log_lines, "未找到需要发送第三天/第五天提醒的订单")
            if mark_run_date:
                _save_printer_config_value(db, "printer_third_day_notify_last_run_date", run_date)
                db.commit()
            payload = {
                "status": "success",
                "run_date": run_date,
                "target_date": target_date,
                "trigger_type": trigger_type,
                "order_count": 0,
                "sent_group_count": 0,
                "sent_customer_count": 0,
                "orders": [],
            }
            _update_scheduled_task_log(
                db,
                log_id,
                status="success",
                summary="未找到需提醒订单",
                log_text="\n".join(log_lines),
                result_json=_json_text(payload),
            )
            payload["log_id"] = log_id
            return payload

        sent_group_count = 0
        sent_customer_count = 0
        notified_orders: list[str] = []
        for order_no, meta in third_day_groups.items():
            customer_name = meta.get("customer_name") or "-"
            erp_customer_id = str(meta.get("erp_customer_id") or "").strip()
            order_date_text = str(meta.get("order_date") or target_date).strip() or target_date
            item_lines = meta.get("items") or []
            content_lines = [
                "⚠️ 第三天未完全发货提醒",
                f"订单号：{order_no}",
                f"客户：{customer_name}",
                f"下单日期：{order_date_text}",
                "未发款式：",
            ]
            for idx, item_text in enumerate(item_lines[:20], start=1):
                content_lines.append(f"{idx}. {item_text}")
            if len(item_lines) > 20:
                content_lines.append(f"... 其余 {len(item_lines) - 20} 款请到系统查看")
            sent = await send_to_notification_groups(db, "\n".join(content_lines))
            sent_group_count += int(sent or 0)
            notified_orders.append(order_no)
            _append_schedule_log(log_lines, f"订单 {order_no} 已发送提醒，成功通知群数量：{sent}")

            customer_room_targets = _list_customer_room_targets(db, erp_customer_id, customer_name)
            if not customer_room_targets:
                _append_schedule_log(log_lines, f"订单 {order_no} 未找到已绑定的客户群，跳过客户确认消息")
                continue

            customer_confirm_lines = [
                "您好，跟您确认一下这张订单的待发情况。",
                f"订单号：{order_no}",
                f"下单日期：{order_date_text}",
                "目前还有以下款式未发：",
            ]
            for idx, item_text in enumerate(item_lines[:20], start=1):
                customer_confirm_lines.append(f"{idx}. {item_text}")
            if len(item_lines) > 20:
                customer_confirm_lines.append(f"... 其余 {len(item_lines) - 20} 款请到系统查看")
            customer_confirm_lines.append("请您确认一下：这张单未发部分是继续帮您配货，还是取消即可？")
            customer_confirm_lines.append("如需调整，请直接在群里回复我们。")
            customer_message = "\n".join(customer_confirm_lines)

            order_customer_sent = 0
            for target in customer_room_targets:
                room_id = str(target.get("room_id") or "").strip()
                if not room_id:
                    continue
                try:
                    send_result = await send_room_at(
                        db,
                        room_id,
                        customer_message,
                        instance_id=int(target["instance_id"]) if target.get("instance_id") else None,
                    )
                    if send_result.get("ok"):
                        order_customer_sent += 1
                        _upsert_customer_order_followup(
                            db,
                            order_no=order_no,
                            room_id=room_id,
                            instance_id=int(target["instance_id"]) if target.get("instance_id") else None,
                            customer_id=int(target["customer_id"]) if target.get("customer_id") else None,
                            customer_name=str(target.get("customer_name") or customer_name),
                            erp_customer_id=erp_customer_id,
                            order_date=order_date_text,
                            current_stage="third_day",
                            followup_status="pending_customer",
                            ask_date=run_date,
                            item_lines=item_lines,
                        )
                    else:
                        _append_schedule_log(
                            log_lines,
                            f"订单 {order_no} 客户群发送失败 room={room_id}: {send_result.get('error') or 'unknown_error'}",
                        )
                except Exception as exc:
                    _append_schedule_log(log_lines, f"订单 {order_no} 客户群发送异常 room={room_id}: {exc}")
            sent_customer_count += order_customer_sent
            _append_schedule_log(log_lines, f"订单 {order_no} 已发送客户确认消息，成功客户群数量：{order_customer_sent}")

        due_followup_map: dict[str, list[dict[str, Any]]] = {}
        for row in due_followup_rows:
            order_no = str(row.get("order_no") or "").strip()
            if not order_no or order_no not in fifth_day_groups:
                continue
            due_followup_map.setdefault(order_no, []).append(dict(row))

        for order_no, rows in due_followup_map.items():
            meta = fifth_day_groups.get(order_no) or {}
            customer_name = meta.get("customer_name") or str(rows[0].get("customer_name") or "-")
            order_date_text = str(meta.get("order_date") or rows[0].get("order_date") or "").strip()
            item_lines = meta.get("items") or []
            notify_lines = [
                "⚠️ 继续发货后第5天仍未完全发货提醒",
                f"订单号：{order_no}",
                f"客户：{customer_name}",
                f"下单日期：{order_date_text or '-'}",
                "未发款式：",
            ]
            for idx, item_text in enumerate(item_lines[:20], start=1):
                notify_lines.append(f"{idx}. {item_text}")
            if len(item_lines) > 20:
                notify_lines.append(f"... 其余 {len(item_lines) - 20} 款请到系统查看")
            sent = await send_to_notification_groups(db, "\n".join(notify_lines))
            sent_group_count += int(sent or 0)
            notified_orders.append(order_no)
            _append_schedule_log(log_lines, f"订单 {order_no} 第五天提醒已发送通知群，成功数量：{sent}")

            customer_message_lines = [
                "这边再跟您确认一下这张订单的未发部分。",
                f"订单号：{order_no}",
                "目前这些款式还没有发完：",
            ]
            for idx, item_text in enumerate(item_lines[:20], start=1):
                customer_message_lines.append(f"{idx}. {item_text}")
            if len(item_lines) > 20:
                customer_message_lines.append(f"... 其余 {len(item_lines) - 20} 款请到系统查看")
            customer_message_lines.append("麻烦您再确认一下，这部分是继续帮您配，还是取消这张单的未发部分呢？")
            customer_message = "\n".join(customer_message_lines)

            order_customer_sent = 0
            for target in rows:
                room_id = str(target.get("room_id") or "").strip()
                if not room_id:
                    continue
                try:
                    send_result = await send_room_at(
                        db,
                        room_id,
                        customer_message,
                        instance_id=int(target["instance_id"]) if target.get("instance_id") else None,
                    )
                    if send_result.get("ok"):
                        order_customer_sent += 1
                        db.execute(
                            text(
                                "UPDATE customer_order_followups SET current_stage = 'fifth_day', followup_status = 'pending_customer', "
                                "last_asked_date = :last_asked_date, ask_count = ask_count + 1, item_summary_json = :item_summary_json, updated_at = NOW() WHERE id = :id"
                            ),
                            {
                                "id": int(target["id"]),
                                "last_asked_date": run_date,
                                "item_summary_json": _json_text(item_lines),
                            },
                        )
                    else:
                        _append_schedule_log(log_lines, f"订单 {order_no} 第五天客户群发送失败 room={room_id}: {send_result.get('error') or 'unknown_error'}")
                except Exception as exc:
                    _append_schedule_log(log_lines, f"订单 {order_no} 第五天客户群发送异常 room={room_id}: {exc}")
            if order_customer_sent:
                db.commit()
            sent_customer_count += order_customer_sent
            _append_schedule_log(log_lines, f"订单 {order_no} 第五天客户确认消息发送成功数量：{order_customer_sent}")

        if mark_run_date:
            _save_printer_config_value(db, "printer_third_day_notify_last_run_date", run_date)
            db.commit()
            _append_schedule_log(log_lines, f"已记录第三天提醒任务执行日期：{run_date}")

        payload = {
            "status": "success",
            "run_date": run_date,
            "target_date": target_date,
            "trigger_type": trigger_type,
            "order_count": len(set(notified_orders)),
            "sent_group_count": sent_group_count,
            "sent_customer_count": sent_customer_count,
            "orders": notified_orders,
        }
        _update_scheduled_task_log(
            db,
            log_id,
            status="success",
            summary=f"已提醒 {len(set(notified_orders))} 个订单",
            log_text="\n".join(log_lines),
            result_json=_json_text(payload),
        )
        payload["log_id"] = log_id
        return payload
    except Exception as exc:
        _append_schedule_log(log_lines, f"执行失败：{exc}")
        if log_id:
            _update_scheduled_task_log(
                db,
                log_id,
                status="failed",
                summary=f"执行失败：{str(exc)[:200]}",
                log_text="\n".join(log_lines),
                result_json=_json_text({
                    "status": "failed",
                    "run_date": run_date,
                    "target_date": target_date,
                    "trigger_type": trigger_type,
                    "error": str(exc),
                }),
            )
        raise
    finally:
        db.close()


def _run_daily_unshipped_schedule_once(trigger_type: str = "scheduled", mark_run_date: bool = True) -> dict[str, Any]:
    db = SessionLocal()
    now = datetime.now()
    run_date = now.strftime("%Y-%m-%d")
    target_date = (now - timedelta(days=1)).strftime("%Y-%m-%d")
    log_lines: list[str] = []
    log_id = 0
    try:
        cfg = get_printer_config(db)
        schedule_time = str(cfg.get("printer_unshipped_schedule_time") or "").strip()
        log_id = _insert_scheduled_task_log(
            db,
            task_key="unshipped_daily",
            run_date=run_date,
            target_date=target_date,
            trigger_type=trigger_type,
            status="running",
            summary="任务执行中",
            log_text="",
            result_json="{}",
        )
        target_client, target_printer = _validate_remote_schedule_target(cfg)
        _append_schedule_log(log_lines, f"开始执行截至昨天仍未发货自动打印 trigger={trigger_type}")
        _append_schedule_log(log_lines, f"统计条件：下单日期 <= {target_date}，且当前未发货数量 > 0")
        _append_schedule_log(log_lines, f"远程打印客户端：{target_client}")
        _append_schedule_log(log_lines, f"远程打印机：{target_printer or '跟随客户端默认打印机'}")
        pre_sync_result = _sync_unshipped_report_before_print(log_lines)
        client_status = get_client_status_by_hostname(target_client)
        if not client_status.get("online"):
            _append_schedule_log(log_lines, f"远程打印客户端当前离线，任务会先入队等待客户端上线：{target_client}")
        result = queue_yesterday_unshipped_orders_for_print(db, target_date)
        if result.get("queued_count", 0) > 0:
            _append_schedule_log(log_lines, f"已按订单入远程打印队列：{', '.join(result.get('orders') or [])}")
            summary = f"成功入队 {result.get('queued_count', 0)} 个订单"
        else:
            _append_schedule_log(log_lines, "未找到符合条件的订单，无需打印")
            summary = "未找到符合条件的订单"
        if mark_run_date:
            _save_printer_config_value(db, "printer_unshipped_schedule_last_run_date", run_date)
            _append_schedule_log(log_lines, f"已记录今日执行日期：{run_date}")
        db.commit()
        payload = {
            "status": "success",
            "run_date": run_date,
            "target_date": target_date,
            "schedule_time": schedule_time,
            "trigger_type": trigger_type,
            "pre_sync_unshipped": pre_sync_result,
            **result,
        }
        _update_scheduled_task_log(
            db,
            log_id,
            status="success",
            summary=summary,
            log_text="\n".join(log_lines),
            result_json=_json_text(payload),
        )
        payload["log_id"] = log_id
        return payload
    except Exception as exc:
        _append_schedule_log(log_lines, f"执行失败：{exc}")
        if log_id:
            _update_scheduled_task_log(
                db,
                log_id,
                status="failed",
                summary=f"执行失败：{str(exc)[:200]}",
                log_text="\n".join(log_lines),
                result_json=_json_text({
                    "status": "failed",
                    "run_date": run_date,
                    "target_date": target_date,
                    "trigger_type": trigger_type,
                    "error": str(exc),
                }),
            )
        raise
    finally:
        db.close()


def trigger_unshipped_schedule_run(trigger_type: str = "manual_test", mark_run_date: bool = False) -> dict[str, Any]:
    global _scheduled_unshipped_running
    if _scheduled_unshipped_running:
        raise ValueError("定时任务正在执行中，请稍后再试")
    _scheduled_unshipped_running = True
    try:
        return _run_daily_unshipped_schedule_once(trigger_type=trigger_type, mark_run_date=mark_run_date)
    finally:
        _scheduled_unshipped_running = False


async def _check_and_run_due_schedule(*, on_startup: bool) -> None:
    db = SessionLocal()
    try:
        cfg = get_printer_config(db)
    finally:
        db.close()

    enabled = _is_true(cfg.get("printer_unshipped_schedule_enabled"))
    schedule_time = str(cfg.get("printer_unshipped_schedule_time") or "").strip()
    last_run_date = str(cfg.get("printer_unshipped_schedule_last_run_date") or "").strip()
    if not enabled or not _is_valid_schedule_time(schedule_time) or _scheduled_unshipped_running:
        return

    now = datetime.now()
    today = now.strftime("%Y-%m-%d")
    if not _is_schedule_effective_today(cfg, today):
        return
    scheduled_at = datetime.strptime(f"{today} {schedule_time}", "%Y-%m-%d %H:%M")
    if now < scheduled_at:
        return

    trigger_type = "startup_catchup" if on_startup else "scheduled"
    notify_last_run_date = str(cfg.get("printer_third_day_notify_last_run_date") or "").strip()
    if last_run_date == today and notify_last_run_date == today:
        return
    logger.info("[定时任务] 命中执行条件，开始处理每日自动任务 trigger=%s time=%s", trigger_type, schedule_time)
    if last_run_date != today:
        try:
            result = await run_in_threadpool(lambda: trigger_unshipped_schedule_run(trigger_type=trigger_type, mark_run_date=True))
            logger.info("[定时任务] 截至昨天仍未发货自动打印完成: %s", result)
        except Exception as exc:
            logger.warning("[定时任务] 截至昨天仍未发货自动打印失败: %s", exc, exc_info=True)
    if notify_last_run_date != today:
        try:
            notify_result = await _run_third_day_unshipped_notify_once(trigger_type=trigger_type, mark_run_date=True)
            logger.info("[定时任务] 第三天未完全发货提醒完成: %s", notify_result)
        except Exception as exc:
            logger.warning("[定时任务] 第三天未完全发货提醒失败: %s", exc, exc_info=True)


async def _scheduled_unshipped_loop() -> None:
    await _check_and_run_due_schedule(on_startup=True)
    while True:
        try:
            await _check_and_run_due_schedule(on_startup=False)
            await asyncio.sleep(30)
        except asyncio.CancelledError:
            logger.info("[定时任务] 截至昨天仍未发货自动打印循环已停止")
            raise
        except Exception as exc:
            logger.warning("[定时任务] 截至昨天仍未发货自动打印循环异常: %s", exc, exc_info=True)
            await asyncio.sleep(30)


def start_unshipped_schedule_task() -> None:
    global _scheduled_unshipped_task
    if _scheduled_unshipped_task is not None and not _scheduled_unshipped_task.done():
        return
    _scheduled_unshipped_task = asyncio.create_task(_scheduled_unshipped_loop())
    logger.info("[定时任务] 截至昨天仍未发货自动打印任务已启动")


def stop_unshipped_schedule_task() -> None:
    global _scheduled_unshipped_task
    if _scheduled_unshipped_task and not _scheduled_unshipped_task.done():
        _scheduled_unshipped_task.cancel()
    _scheduled_unshipped_task = None


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


def enqueue_existing_pdf(db: Session, order_no: str, doc_type: str = "picking", pdf_object: str = "") -> dict[str, Any]:
    """将已生成的 PDF 入队（不重复生成），由打印客户端取走打印"""
    ensure_printer_tables(db)
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
    logger.info("打印任务已入队(existing): order=%s doc_type=%s obj=%s", order_no, doc_type, pdf_object)
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
        # 记录纸张已打印
        _record_printed_pages_for_job(db, job_id)
    else:
        db.execute(
            text(
                "UPDATE print_queue SET status = IF(attempts + 1 >= 3, 'failed', 'failed'), "
                "attempts = attempts + 1, error_msg = :err, updated_at = NOW() WHERE id = :id"
            ),
            {"id": job_id, "err": error[:500]},
        )
    db.commit()


def _record_printed_pages_for_job(db: Session, job_id: int) -> None:
    """打印成功后，将该任务关联的所有活跃 page_id 写入 paper_print_records"""
    from app.services.downstream_support import ensure_downstream_support_tables
    ensure_downstream_support_tables(db)
    job = db.execute(
        text("SELECT order_no, doc_type FROM print_queue WHERE id = :id"),
        {"id": job_id},
    ).mappings().first()
    if not job:
        return
    order_no = job["order_no"]
    doc_type = job["doc_type"] or "picking"

    # 根据 doc_type 查询对应的 pages 表
    if doc_type == "picking":
        pages_table = "picking_print_pages"
    elif doc_type == "unshipped":
        pages_table = "unshipped_print_pages"
    else:
        return

    pages = db.execute(
        text(f"SELECT page_id, barcode_content FROM {pages_table} WHERE order_no = :no AND status = 'active'"),
        {"no": order_no},
    ).mappings().all()

    for p in pages:
        try:
            db.execute(
                text(
                    "INSERT INTO paper_print_records (paper_id, order_no, doc_type, barcode_content, print_job_id) "
                    "VALUES (:pid, :ono, :dt, :bc, :jid) "
                    "ON DUPLICATE KEY UPDATE print_job_id = VALUES(print_job_id), printed_at = NOW()"
                ),
                {
                    "pid": p["page_id"],
                    "ono": order_no,
                    "dt": doc_type,
                    "bc": p["barcode_content"] or "",
                    "jid": job_id,
                },
            )
        except Exception as exc:
            logger.warning("记录纸张打印状态失败: page_id=%s err=%s", p["page_id"], exc)


def is_paper_printed(db: Session, paper_id: str) -> bool:
    """检查纸张ID是否已打印"""
    row = db.execute(
        text("SELECT id FROM paper_print_records WHERE paper_id = :pid LIMIT 1"),
        {"pid": paper_id},
    ).first()
    return row is not None


def record_paper_printed(db: Session, paper_id: str, order_no: str, doc_type: str,
                         barcode_content: str = "", print_job_id: int | None = None) -> None:
    """手动记录纸张已打印（用于不走 print_queue 的场景）"""
    db.execute(
        text(
            "INSERT INTO paper_print_records (paper_id, order_no, doc_type, barcode_content, print_job_id) "
            "VALUES (:pid, :ono, :dt, :bc, :jid) "
            "ON DUPLICATE KEY UPDATE print_job_id = VALUES(print_job_id), printed_at = NOW()"
        ),
        {"pid": paper_id, "ono": order_no, "dt": doc_type, "bc": barcode_content, "jid": print_job_id},
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
