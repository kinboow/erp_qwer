"""
ERP 销售订单定时同步服务
每隔 N 分钟从弘兆云 ERP 拉取销售订单列表及详情，存入本地数据库。
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timedelta
from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import settings
from app.database import SessionLocal, run_in_threadpool
from app.ncloud.client.erp_client import ERPClient
from app.ncloud.services.base import list_products as erp_list_products
from app.ncloud.services.inventory import query_inventory as erp_query_inventory
from app.ncloud.services.sales_orders import get_order_detail, list_orders
from app.ncloud.services.shipments import get_shipment_detail, list_shipments
from app.ncloud.services.unshipped_report import query_unshipped_report as erp_query_unshipped
from app.services.system_activities import create_activity_background
from app.services.system_messages import create_system_message_background

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# DDL — 自动建表
# ---------------------------------------------------------------------------

_DDL_ORDERS = """
CREATE TABLE IF NOT EXISTS erp_sales_orders (
    id              BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    order_no        VARCHAR(100) NOT NULL,
    order_date      VARCHAR(50)  DEFAULT '',
    state           INT          NOT NULL DEFAULT 0,
    customer_id     VARCHAR(100) DEFAULT '',
    customer_name   VARCHAR(255) DEFAULT '',
    customer_tel    VARCHAR(100) DEFAULT '',
    customer_addr   VARCHAR(500) DEFAULT '',
    salesperson     VARCHAR(100) DEFAULT '',
    creator         VARCHAR(100) DEFAULT '',
    order_ref       VARCHAR(100) DEFAULT '',
    delivery_date   VARCHAR(50)  DEFAULT '',
    shipping_method VARCHAR(100) DEFAULT '',
    shipping_tel    VARCHAR(100) DEFAULT '',
    shipping_addr   VARCHAR(500) DEFAULT '',
    currency        VARCHAR(50)  DEFAULT '',
    brand           VARCHAR(100) DEFAULT '',
    customer_type   VARCHAR(100) DEFAULT '',
    contact_person  VARCHAR(100) DEFAULT '',
    plan            VARCHAR(10)  DEFAULT '',
    price_print     INT          DEFAULT NULL,
    total_qty       DECIMAL(12,2) DEFAULT 0,
    total_amount    DECIMAL(12,2) DEFAULT 0,
    payment_amount  DECIMAL(12,2) DEFAULT NULL,
    discount_amount DECIMAL(12,2) DEFAULT NULL,
    print_count     INT          DEFAULT 0,
    product_no      VARCHAR(255) DEFAULT '',
    remark          TEXT NULL,
    synced_at       DATETIME DEFAULT CURRENT_TIMESTAMP,
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_order_no (order_no),
    INDEX idx_customer_id (customer_id),
    INDEX idx_order_date (order_date),
    INDEX idx_state (state),
    INDEX idx_synced_at (synced_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
"""

_DDL_ITEMS = """
CREATE TABLE IF NOT EXISTS erp_sales_order_items (
    id                  BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    order_no            VARCHAR(100) NOT NULL,
    erp_item_id         VARCHAR(100) DEFAULT '',
    sort_index          INT          NOT NULL DEFAULT 0,
    brand               VARCHAR(100) DEFAULT '',
    product_no          VARCHAR(100) DEFAULT '',
    product_name        VARCHAR(255) DEFAULT '',
    color               VARCHAR(100) DEFAULT '',
    grade               VARCHAR(100) DEFAULT '',
    customer_product_no VARCHAR(100) DEFAULT '',
    packaging           VARCHAR(100) DEFAULT '',
    unit                VARCHAR(50)  DEFAULT '',
    price               DECIMAL(12,2) DEFAULT 0,
    discount            INT          DEFAULT 100,
    sizes_json          TEXT NULL,
    total_qty           DECIMAL(12,2) DEFAULT 0,
    remark              TEXT NULL,
    created_at          DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at          DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_order_no  (order_no),
    INDEX idx_product_no (product_no),
    INDEX idx_erp_item_id (erp_item_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
"""


_DDL_SHIPMENTS = """
CREATE TABLE IF NOT EXISTS erp_sales_shipments (
    id              BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    order_no        VARCHAR(100) NOT NULL,
    order_date      VARCHAR(50)  DEFAULT '',
    state           INT          NOT NULL DEFAULT 0,
    customer_id     VARCHAR(100) DEFAULT '',
    customer_name   VARCHAR(255) DEFAULT '',
    customer_tel    VARCHAR(100) DEFAULT '',
    customer_addr   VARCHAR(500) DEFAULT '',
    salesperson     VARCHAR(100) DEFAULT '',
    creator         VARCHAR(100) DEFAULT '',
    handler         VARCHAR(100) DEFAULT '',
    warehouse       VARCHAR(100) DEFAULT '',
    shipping_method VARCHAR(100) DEFAULT '',
    shipping_tel    VARCHAR(100) DEFAULT '',
    shipping_addr   VARCHAR(500) DEFAULT '',
    tracking_no     VARCHAR(200) DEFAULT '',
    delivery_person VARCHAR(100) DEFAULT '',
    contact_person  VARCHAR(100) DEFAULT '',
    contact_tel     VARCHAR(100) DEFAULT '',
    currency        VARCHAR(50)  DEFAULT '',
    customer_type   VARCHAR(100) DEFAULT '',
    price_print     INT          DEFAULT NULL,
    freight         DECIMAL(12,2) DEFAULT NULL,
    payment_amount  DECIMAL(12,2) DEFAULT NULL,
    total_qty       DECIMAL(12,2) DEFAULT 0,
    total_amount    DECIMAL(12,2) DEFAULT 0,
    remark          TEXT NULL,
    synced_at       DATETIME DEFAULT CURRENT_TIMESTAMP,
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_order_no (order_no),
    INDEX idx_customer_id (customer_id),
    INDEX idx_order_date (order_date),
    INDEX idx_state (state),
    INDEX idx_synced_at (synced_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
"""

_DDL_SHIPMENT_ITEMS = """
CREATE TABLE IF NOT EXISTS erp_sales_shipment_items (
    id                  BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    order_no            VARCHAR(100) NOT NULL,
    sort_index          INT          NOT NULL DEFAULT 0,
    brand               VARCHAR(100) DEFAULT '',
    product_no          VARCHAR(100) DEFAULT '',
    product_name        VARCHAR(255) DEFAULT '',
    color               VARCHAR(100) DEFAULT '',
    customer_product_no VARCHAR(100) DEFAULT '',
    packaging           VARCHAR(100) DEFAULT '',
    unit                VARCHAR(50)  DEFAULT '',
    price               DECIMAL(12,2) DEFAULT 0,
    discount            INT          DEFAULT 100,
    order_ref           VARCHAR(100) DEFAULT '',
    sizes_json          TEXT NULL,
    total_qty           DECIMAL(12,2) DEFAULT 0,
    remark              TEXT NULL,
    created_at          DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at          DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_order_no  (order_no),
    INDEX idx_product_no (product_no)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
"""


_DDL_PRODUCTS = """
CREATE TABLE IF NOT EXISTS erp_products (
    id              BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    product_id      VARCHAR(100) NOT NULL,
    product_no      VARCHAR(200) DEFAULT '',
    product_name    VARCHAR(255) DEFAULT '',
    brand           VARCHAR(200) DEFAULT '',
    category        VARCHAR(200) DEFAULT '',
    color           TEXT NULL,
    unit            VARCHAR(50)  DEFAULT '',
    price           DECIMAL(12,2) DEFAULT 0,
    spec            TEXT NULL,
    material        VARCHAR(200) DEFAULT '',
    image_url       VARCHAR(500) DEFAULT '',
    remark          TEXT NULL,
    is_current_year TINYINT NOT NULL DEFAULT 0,
    synced_at       DATETIME DEFAULT CURRENT_TIMESTAMP,
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_product_id (product_id),
    INDEX idx_product_no (product_no),
    INDEX idx_is_current_year (is_current_year)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
"""


_DDL_INVENTORY = """
CREATE TABLE IF NOT EXISTS erp_inventory (
    id              BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    warehouse       VARCHAR(100) NOT NULL DEFAULT '',
    product_type    VARCHAR(100) DEFAULT '',
    product_no      VARCHAR(200) NOT NULL DEFAULT '',
    product_name    VARCHAR(255) DEFAULT '',
    material        VARCHAR(200) DEFAULT '',
    image_url       VARCHAR(500) DEFAULT '',
    color           VARCHAR(200) DEFAULT '',
    unit            VARCHAR(50)  DEFAULT '',
    qty             DECIMAL(14,2) DEFAULT 0,
    sale_price      DECIMAL(12,2) DEFAULT 0,
    cost_price      DECIMAL(12,2) DEFAULT 0,
    amount          DECIMAL(14,2) DEFAULT 0,
    in_transit_qty  DECIMAL(14,2) DEFAULT 0,
    sizes_json      TEXT NULL,
    synced_at       DATETIME DEFAULT CURRENT_TIMESTAMP,
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_wh_pno_color (warehouse, product_no, color),
    INDEX idx_product_no (product_no),
    INDEX idx_warehouse (warehouse),
    INDEX idx_synced_at (synced_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
"""


_DDL_PRODUCT_NAME_MAPPINGS = """
CREATE TABLE IF NOT EXISTS product_name_mappings (
    id              BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    product_no      VARCHAR(200) NOT NULL COMMENT '货号',
    alias_name      VARCHAR(255) NOT NULL COMMENT '映射名称',
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uk_alias_name (alias_name),
    INDEX idx_product_no (product_no)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
"""


_DDL_UNSHIPPED_REPORT = """
CREATE TABLE IF NOT EXISTS erp_unshipped_report (
    id              BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    erp_row_id      VARCHAR(100) NOT NULL DEFAULT '',
    order_no        VARCHAR(100) NOT NULL DEFAULT '',
    order_date      VARCHAR(20)  DEFAULT '',
    customer_id     VARCHAR(100) DEFAULT '',
    customer_type   VARCHAR(100) DEFAULT '',
    customer_order_no VARCHAR(200) DEFAULT '',
    brand           VARCHAR(200) DEFAULT '',
    product_no      VARCHAR(200) NOT NULL DEFAULT '',
    product_name    VARCHAR(255) DEFAULT '',
    color           VARCHAR(200) DEFAULT '',
    unit            VARCHAR(50)  DEFAULT '',
    order_qty       DECIMAL(14,2) DEFAULT 0,
    shipped_qty     DECIMAL(14,2) DEFAULT 0,
    returned_qty    DECIMAL(14,2) DEFAULT 0,
    unshipped_qty   DECIMAL(14,2) DEFAULT 0,
    unshipped_amount DECIMAL(14,2) DEFAULT 0,
    stock_qty       DECIMAL(14,2) DEFAULT 0,
    price           DECIMAL(12,2) DEFAULT 0,
    cost_price      DECIMAL(12,2) DEFAULT 0,
    tag_price       DECIMAL(12,2) DEFAULT 0,
    creator         VARCHAR(100) DEFAULT '',
    remark          TEXT NULL,
    unshipped_sizes_json TEXT NULL,
    order_sizes_json     TEXT NULL,
    synced_at       DATETIME DEFAULT CURRENT_TIMESTAMP,
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_erp_row_id (erp_row_id),
    INDEX idx_order_no (order_no),
    INDEX idx_order_date (order_date),
    INDEX idx_customer_id (customer_id),
    INDEX idx_product_no (product_no),
    INDEX idx_synced_at (synced_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
"""


_DDL_SYNC_CONFIG = """
CREATE TABLE IF NOT EXISTS erp_sync_config (
    id              INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    config_key      VARCHAR(100) NOT NULL UNIQUE,
    config_value    TEXT NULL,
    updated_at      DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
"""

_CONFIG_DEFAULTS = {
    "erp_base_url": "",
    "erp_username": "",
    "erp_password": "",
    "erp_qr_image_path": "",
    "sync_interval_minutes": "15",
    "sync_days_back": "360",
    "sync_enabled": "true",
}


def ensure_tables(db: Session) -> None:
    """确保同步表存在"""
    db.execute(text(_DDL_ORDERS))
    db.execute(text(_DDL_ITEMS))
    db.execute(text(_DDL_SHIPMENTS))
    db.execute(text(_DDL_SHIPMENT_ITEMS))
    db.execute(text(_DDL_PRODUCTS))
    db.execute(text(_DDL_INVENTORY))
    db.execute(text(_DDL_UNSHIPPED_REPORT))
    db.execute(text(_DDL_SYNC_CONFIG))
    db.execute(text(_DDL_PRODUCT_NAME_MAPPINGS))
    # 补加字段（已有表结构升级）
    _alter_cmds = [
        ("erp_sales_orders", "print_count", "INT DEFAULT 0"),
        ("erp_sales_orders", "product_no", "VARCHAR(255) DEFAULT ''"),
        ("erp_sales_order_items", "erp_item_id", "VARCHAR(100) DEFAULT '' AFTER order_no"),
        ("erp_products", "is_current_year", "TINYINT NOT NULL DEFAULT 0 AFTER remark"),
    ]
    for tbl, col, defn in _alter_cmds:
        try:
            db.execute(text(f"ALTER TABLE {tbl} ADD COLUMN {col} {defn}"))
        except Exception:
            pass  # 已存在则跳过
    # 补加索引
    try:
        db.execute(text("CREATE INDEX idx_erp_item_id ON erp_sales_order_items (erp_item_id)"))
    except Exception:
        pass
    db.commit()


# ---------------------------------------------------------------------------
# 配置读写（数据库）
# ---------------------------------------------------------------------------

def get_erp_sync_config(db: Session) -> dict[str, Any]:
    """从数据库读取 ERP 同步配置，不存在的 key 用默认值填充"""
    ensure_tables(db)
    rows = db.execute(text("SELECT config_key, config_value FROM erp_sync_config")).mappings().all()
    cfg = {r["config_key"]: r["config_value"] for r in rows}
    for k, v in _CONFIG_DEFAULTS.items():
        cfg.setdefault(k, v)
    # 转换类型
    cfg["sync_interval_minutes"] = int(cfg.get("sync_interval_minutes") or 15)
    cfg["sync_days_back"] = int(cfg.get("sync_days_back") or 360)
    cfg["sync_enabled"] = str(cfg.get("sync_enabled", "true")).lower() in ("true", "1", "yes")
    return cfg


def save_erp_sync_config(db: Session, data: dict[str, Any]) -> dict[str, Any]:
    """写入 ERP 同步配置到数据库（只更新传入的 key）"""
    ensure_tables(db)
    for key, value in data.items():
        if key not in _CONFIG_DEFAULTS:
            continue
        str_value = str(value) if value is not None else ""
        existing = db.execute(
            text("SELECT id FROM erp_sync_config WHERE config_key = :key"),
            {"key": key},
        ).mappings().first()
        if existing:
            db.execute(
                text("UPDATE erp_sync_config SET config_value = :val WHERE config_key = :key"),
                {"key": key, "val": str_value},
            )
        else:
            db.execute(
                text("INSERT INTO erp_sync_config (config_key, config_value) VALUES (:key, :val)"),
                {"key": key, "val": str_value},
            )
    db.commit()
    return get_erp_sync_config(db)


def _get_db_config() -> dict[str, Any]:
    """便捷方法：打开一个临时 session 读取配置"""
    db = SessionLocal()
    try:
        return get_erp_sync_config(db)
    finally:
        db.close()


# ---------------------------------------------------------------------------
# ERPClient 热重载
# ---------------------------------------------------------------------------

async def reload_erp_client(app: Any) -> None:
    """根据数据库配置重新创建 ERPClient（保存配置后调用）"""
    import httpx
    cfg = _get_db_config()
    # 更新 ncloud config proxy
    from app.ncloud.config import settings as ncloud_settings
    ncloud_settings._override = {
        "NCLOUD_BASE_URL": cfg.get("erp_base_url") or "",
        "NCLOUD_USERNAME": cfg.get("erp_username") or "",
        "NCLOUD_PASSWORD": cfg.get("erp_password") or "",
        "NCLOUD_QR_IMAGE_PATH": cfg.get("erp_qr_image_path") or "",
    }
    # 关闭旧 client
    old_http = getattr(app.state, "http_client", None)
    if old_http:
        try:
            await old_http.aclose()
        except Exception:
            pass
    # 创建新 client
    http_client = httpx.AsyncClient(
        headers={
            "User-Agent": "ncloud2api/0.2",
            "Accept": "application/json, text/javascript, */*; q=0.01",
        },
        follow_redirects=False,
        trust_env=False,
        timeout=httpx.Timeout(30, connect=10),
    )
    erp_client = ERPClient(http_client)
    app.state.http_client = http_client
    app.state.erp_client = erp_client
    logger.info("[ERP Sync] ERPClient 已重载, base_url=%s", cfg.get("erp_base_url"))


def restart_sync_scheduler(app: Any) -> None:
    """根据数据库配置重启定时同步"""
    global _sync_task
    cfg = _get_db_config()
    # 取消旧任务
    if _sync_task and not _sync_task.done():
        _sync_task.cancel()
        _sync_task = None
    if not cfg.get("sync_enabled", True):
        logger.info("[ERP Sync] 同步已禁用")
        return
    if not cfg.get("erp_base_url"):
        logger.info("[ERP Sync] 未配置 erp_base_url，跳过自动同步")
        return
    erp_client = getattr(app.state, "erp_client", None)
    if not erp_client:
        return
    _sync_task = asyncio.create_task(_sync_loop(erp_client))
    logger.info("[ERP Sync] 定时同步已重启，间隔 %s 分钟", cfg.get("sync_interval_minutes", 15))


# ---------------------------------------------------------------------------
# 同步核心逻辑
# ---------------------------------------------------------------------------

async def sync_sales_orders(erp_client: ERPClient, days_back: int | None = None) -> dict[str, Any]:
    """
    拉取 ERP 销售订单列表 + 每张订单的详情，写入本地数据库。
    使用滑动时间窗口向前回溯，直到某个窗口返回 0 条记录时停止。
    返回同步统计信息。
    """
    cfg = _get_db_config()
    window_days = days_back or cfg.get("sync_days_back", 360)
    # 短周期（<=180天，即定时同步）：找到数据就停，空窗口顺延
    # 长周期（>180天，即手动同步）：完整滑动窗口回溯
    stop_on_data = window_days <= 180

    db: Session = SessionLocal()
    try:
        ensure_tables(db)

        # 1. 获取销售订单列表
        list_data: dict[str, Any] = {}  # order_no -> list item data
        window_end = datetime.now()
        total_windows = 0
        consecutive_empty = 0

        while True:
            datee = window_end.strftime("%Y-%m-%d")
            dates = (window_end - timedelta(days=window_days)).strftime("%Y-%m-%d")
            total_windows += 1

            window_count = 0
            page = 1
            rows_per_page = 200
            while True:
                order_list = await list_orders(
                    erp_client,
                    dates=dates,
                    datee=datee,
                    state=["0", "1"],
                    page=page,
                    rows=rows_per_page,
                )
                for item in order_list.rows:
                    list_data[item.order_no] = {
                        "customer_name": item.customer_name or "",
                        "customer_tel": item.customer_tel or "",
                        "customer_id": item.customer_id or "",
                        "salesperson": item.salesperson or "",
                        "creator": item.creator or "",
                        "total_qty": item.total_qty or 0,
                        "total_amount": item.total_amount or 0,
                        "print_count": item.print_count or 0,
                        "product_no": item.product_no or "",
                    }
                    window_count += 1
                if page * rows_per_page >= order_list.total:
                    break
                page += 1

            logger.info("[ERP Sync] 销售订单窗口 %s ~ %s 获取 %d 条", dates, datee, window_count)

            if window_count > 0 and stop_on_data:
                break  # 定时同步：找到数据就停，不继续滑动

            if window_count == 0:
                consecutive_empty += 1
                if consecutive_empty >= 3:
                    break
            else:
                consecutive_empty = 0

            window_end = window_end - timedelta(days=window_days) - timedelta(days=1)

        all_order_nos = list(list_data.keys())
        logger.info("[ERP Sync] 获取到 %d 张销售订单（共 %d 个窗口）", len(all_order_nos), total_windows)

        synced = 0
        failed = 0
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # 2. 并发获取详情（5 路并行 + 重试），串行写入数据库
        sem = asyncio.Semaphore(5)

        async def _fetch_one(order_no: str) -> tuple[str, Any | None, Exception | None]:
            async with sem:
                last_exc: Exception | None = None
                for attempt in range(3):
                    try:
                        detail = await get_order_detail(erp_client, order_no)
                        return (order_no, detail, None)
                    except Exception as exc:
                        last_exc = exc
                        if attempt < 2:
                            await asyncio.sleep(1.5 * (attempt + 1))
                return (order_no, None, last_exc)

        results_list = await asyncio.gather(*[_fetch_one(no) for no in all_order_nos])

        for order_no, detail, exc in results_list:
            if exc is not None:
                logger.warning("[ERP Sync] 同步订单 %s 失败: %s", order_no, exc)
                failed += 1
                continue
            try:
                await run_in_threadpool(_upsert_order, db, detail, now_str, list_extra=list_data.get(order_no))
                synced += 1
            except Exception as db_exc:
                logger.warning("[ERP Sync] 写入订单 %s 失败: %s", order_no, db_exc)
                failed += 1
                try:
                    db.rollback()
                except Exception:
                    pass

        result = {
            "total_windows": total_windows,
            "total_found": len(all_order_nos),
            "synced": synced,
            "failed": failed,
            "synced_at": now_str,
        }
        logger.info("[ERP Sync] 同步完成: %s", result)
        return result

    except Exception as exc:
        logger.exception("[ERP Sync] 同步异常")
        raise
    finally:
        db.close()


def _upsert_order(db: Session, detail: Any, synced_at: str, list_extra: dict | None = None) -> None:
    """插入或更新一张订单（主表 + 明细行）。list_extra 提供列表接口的补充数据。"""
    main = detail.main
    order_no = main.order_no
    extra = list_extra or {}

    # 客户名称兜底：ERP详情 → 列表API → 本地下游客户表
    customer_id = main.customer_id or extra.get("customer_id", "")
    customer_name = main.customer_name or extra.get("customer_name", "")
    customer_tel = main.customer_tel or extra.get("customer_tel", "")
    if not customer_name and customer_id:
        try:
            local = db.execute(
                text("SELECT customer_name, phone FROM downstream_customers WHERE erp_customer_id = :cid LIMIT 1"),
                {"cid": customer_id},
            ).mappings().first()
            if local:
                customer_name = local["customer_name"] or ""
                if not customer_tel:
                    customer_tel = local["phone"] or ""
        except Exception:
            pass

    # 从详情明细行聚合货号（当列表API未提供时使用）
    detail_product_nos = ", ".join(
        dict.fromkeys(row.product_no for row in detail.detail if row.product_no)
    )

    # upsert 主表
    existing = db.execute(
        text("SELECT id, print_count, product_no FROM erp_sales_orders WHERE order_no = :order_no"),
        {"order_no": order_no},
    ).mappings().first()

    order_data = {
        "order_no": order_no,
        "order_date": main.order_date or "",
        "state": main.state,
        "customer_id": customer_id,
        "customer_name": customer_name,
        "customer_tel": customer_tel,
        "customer_addr": main.customer_addr or "",
        "salesperson": main.salesperson or extra.get("salesperson", ""),
        "creator": main.creator or extra.get("creator", ""),
        "order_ref": main.order_ref or "",
        "delivery_date": main.delivery_date or "",
        "shipping_method": main.shipping_method or "",
        "shipping_tel": main.shipping_tel or "",
        "shipping_addr": main.shipping_addr or "",
        "currency": main.currency or "",
        "brand": main.brand or "",
        "customer_type": main.customer_type or "",
        "contact_person": main.contact_person or "",
        "plan": main.plan or "",
        "price_print": main.price_print,
        "total_qty": main.total_qty or 0,
        "total_amount": main.total_amount or 0,
        "payment_amount": main.payment_amount,
        "discount_amount": main.discount_amount,
        "print_count": extra.get("print_count") if extra.get("print_count") is not None else (existing["print_count"] if existing else 0),
        "product_no": extra.get("product_no") or detail_product_nos or (existing["product_no"] if existing else ""),
        "remark": main.remark or "",
        "synced_at": synced_at,
    }

    if existing:
        set_clause = ", ".join(f"{k} = :{k}" for k in order_data if k != "order_no")
        db.execute(
            text(f"UPDATE erp_sales_orders SET {set_clause} WHERE order_no = :order_no"),
            order_data,
        )
    else:
        cols = ", ".join(order_data.keys())
        vals = ", ".join(f":{k}" for k in order_data.keys())
        db.execute(
            text(f"INSERT INTO erp_sales_orders ({cols}) VALUES ({vals})"),
            order_data,
        )

    # 删除旧明细，重新插入
    db.execute(
        text("DELETE FROM erp_sales_order_items WHERE order_no = :order_no"),
        {"order_no": order_no},
    )

    for idx, row in enumerate(detail.detail):
        sizes_list = [{"size": s.size, "qty": s.qty} for s in row.sizes]
        total_qty = sum(s.qty for s in row.sizes)
        item_data = {
            "order_no": order_no,
            "erp_item_id": row.erp_item_id or "",
            "sort_index": idx + 1,
            "brand": row.brand or "",
            "product_no": row.product_no or "",
            "product_name": row.product_name or "",
            "color": row.color or "",
            "grade": row.grade or "",
            "customer_product_no": row.customer_product_no or "",
            "packaging": row.packaging or "",
            "unit": row.unit or "",
            "price": row.price or 0,
            "discount": row.discount or 100,
            "sizes_json": json.dumps(sizes_list, ensure_ascii=False),
            "total_qty": total_qty,
            "remark": row.remark or "",
        }
        cols = ", ".join(item_data.keys())
        vals = ", ".join(f":{k}" for k in item_data.keys())
        db.execute(
            text(f"INSERT INTO erp_sales_order_items ({cols}) VALUES ({vals})"),
            item_data,
        )

    db.commit()


# ---------------------------------------------------------------------------
# 发货单同步
# ---------------------------------------------------------------------------

async def sync_sales_shipments(erp_client: ERPClient, days_back: int | None = None) -> dict[str, Any]:
    """
    拉取 ERP 销售发货单列表 + 每张发货单的详情，写入本地数据库。
    使用滑动时间窗口向前回溯，直到某个窗口返回 0 条记录时停止。
    返回同步统计信息。
    """
    cfg = _get_db_config()
    window_days = days_back or cfg.get("sync_days_back", 360)
    stop_on_data = window_days <= 180

    db: Session = SessionLocal()
    try:
        ensure_tables(db)

        # 1. 获取发货单列表
        list_data: dict[str, Any] = {}  # order_no -> list item data
        window_end = datetime.now()
        total_windows = 0
        consecutive_empty = 0

        while True:
            datee = window_end.strftime("%Y-%m-%d")
            dates = (window_end - timedelta(days=window_days)).strftime("%Y-%m-%d")
            total_windows += 1

            window_count = 0
            page = 1
            rows_per_page = 200
            while True:
                shipment_list = await list_shipments(
                    erp_client,
                    dates=dates,
                    datee=datee,
                    state=["0", "1"],
                    page=page,
                    rows=rows_per_page,
                )
                for item in shipment_list.rows:
                    list_data[item.order_no] = {
                        "customer_name": item.customer_name or "",
                        "customer_id": item.customer_id or "",
                        "salesperson": item.salesperson or "",
                        "total_qty": item.total_qty or 0,
                        "total_amount": item.total_amount or 0,
                        "tracking_no": item.tracking_no or "",
                        "shipping_method": item.shipping_method or "",
                        "freight": item.freight,
                    }
                    window_count += 1
                if page * rows_per_page >= shipment_list.total:
                    break
                page += 1

            logger.info("[ERP Sync] 发货单窗口 %s ~ %s 获取 %d 条", dates, datee, window_count)

            if window_count > 0 and stop_on_data:
                break

            if window_count == 0:
                consecutive_empty += 1
                if consecutive_empty >= 3:
                    break
            else:
                consecutive_empty = 0

            window_end = window_end - timedelta(days=window_days) - timedelta(days=1)

        all_order_nos = list(list_data.keys())
        logger.info("[ERP Sync] 获取到 %d 张销售发货单（共 %d 个窗口）", len(all_order_nos), total_windows)

        synced = 0
        failed = 0
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # 2. 并发获取详情（5 路并行 + 重试），串行写入数据库
        sem = asyncio.Semaphore(5)

        async def _fetch_one(order_no: str) -> tuple[str, Any | None, Exception | None]:
            async with sem:
                last_exc: Exception | None = None
                for attempt in range(3):
                    try:
                        detail = await get_shipment_detail(erp_client, order_no)
                        return (order_no, detail, None)
                    except Exception as exc:
                        last_exc = exc
                        if attempt < 2:
                            await asyncio.sleep(1.5 * (attempt + 1))
                return (order_no, None, last_exc)

        results_list = await asyncio.gather(*[_fetch_one(no) for no in all_order_nos])

        for order_no, detail, exc in results_list:
            if exc is not None:
                logger.warning("[ERP Sync] 同步发货单 %s 失败: %s", order_no, exc)
                failed += 1
                continue
            try:
                await run_in_threadpool(_upsert_shipment, db, detail, now_str, list_extra=list_data.get(order_no))
                synced += 1
            except Exception as db_exc:
                logger.warning("[ERP Sync] 写入发货单 %s 失败: %s", order_no, db_exc)
                failed += 1
                try:
                    db.rollback()
                except Exception:
                    pass

        result = {
            "total_windows": total_windows,
            "total_found": len(all_order_nos),
            "synced": synced,
            "failed": failed,
            "synced_at": now_str,
        }
        logger.info("[ERP Sync] 发货单同步完成: %s", result)
        return result

    except Exception:
        logger.exception("[ERP Sync] 发货单同步异常")
        raise
    finally:
        db.close()


def _upsert_shipment(db: Session, detail: Any, synced_at: str, list_extra: dict | None = None) -> None:
    """插入或更新一张发货单（主表 + 明细行）"""
    main = detail.main
    order_no = main.order_no
    extra = list_extra or {}

    # 客户名称兜底：ERP详情 → 列表API → 本地下游客户表
    customer_id = main.customer_id or extra.get("customer_id", "")
    customer_name = main.customer_name or extra.get("customer_name", "")
    if not customer_name and customer_id:
        try:
            local = db.execute(
                text("SELECT customer_name FROM downstream_customers WHERE erp_customer_id = :cid LIMIT 1"),
                {"cid": customer_id},
            ).mappings().first()
            if local:
                customer_name = local["customer_name"] or ""
        except Exception:
            pass

    existing = db.execute(
        text("SELECT id FROM erp_sales_shipments WHERE order_no = :order_no"),
        {"order_no": order_no},
    ).mappings().first()

    shipment_data = {
        "order_no": order_no,
        "order_date": main.order_date or "",
        "state": main.state,
        "customer_id": customer_id,
        "customer_name": customer_name,
        "customer_tel": main.customer_tel or "",
        "customer_addr": main.customer_addr or "",
        "salesperson": main.salesperson or extra.get("salesperson", ""),
        "creator": main.creator or "",
        "handler": main.handler or "",
        "warehouse": main.warehouse or "",
        "shipping_method": main.shipping_method or extra.get("shipping_method", ""),
        "shipping_tel": main.shipping_tel or "",
        "shipping_addr": main.shipping_addr or "",
        "tracking_no": main.tracking_no or extra.get("tracking_no", ""),
        "delivery_person": main.delivery_person or "",
        "contact_person": main.contact_person or "",
        "contact_tel": main.contact_tel or "",
        "currency": main.currency or "",
        "customer_type": main.customer_type or "",
        "price_print": main.price_print,
        "freight": main.freight if main.freight is not None else extra.get("freight"),
        "payment_amount": main.payment_amount,
        "total_qty": main.total_qty or 0,
        "total_amount": main.total_amount or 0,
        "remark": main.remark or "",
        "synced_at": synced_at,
    }

    if existing:
        set_clause = ", ".join(f"{k} = :{k}" for k in shipment_data if k != "order_no")
        db.execute(
            text(f"UPDATE erp_sales_shipments SET {set_clause} WHERE order_no = :order_no"),
            shipment_data,
        )
    else:
        cols = ", ".join(shipment_data.keys())
        vals = ", ".join(f":{k}" for k in shipment_data.keys())
        db.execute(
            text(f"INSERT INTO erp_sales_shipments ({cols}) VALUES ({vals})"),
            shipment_data,
        )

    # 删除旧明细，重新插入
    db.execute(
        text("DELETE FROM erp_sales_shipment_items WHERE order_no = :order_no"),
        {"order_no": order_no},
    )

    for idx, row in enumerate(detail.detail):
        sizes_list = [{"size": s.size, "qty": s.qty} for s in row.sizes]
        total_qty = sum(s.qty for s in row.sizes)
        item_data = {
            "order_no": order_no,
            "sort_index": idx + 1,
            "brand": row.brand or "",
            "product_no": row.product_no or "",
            "product_name": row.product_name or "",
            "color": row.color or "",
            "customer_product_no": row.customer_product_no or "",
            "packaging": row.packaging or "",
            "unit": row.unit or "",
            "price": row.price or 0,
            "discount": row.discount or 100,
            "order_ref": row.order_ref or "",
            "sizes_json": json.dumps(sizes_list, ensure_ascii=False),
            "total_qty": total_qty,
            "remark": row.remark or "",
        }
        cols = ", ".join(item_data.keys())
        vals = ", ".join(f":{k}" for k in item_data.keys())
        db.execute(
            text(f"INSERT INTO erp_sales_shipment_items ({cols}) VALUES ({vals})"),
            item_data,
        )

    db.commit()


# ---------------------------------------------------------------------------
# 产品同步
# ---------------------------------------------------------------------------

async def sync_products(erp_client: ERPClient) -> dict[str, Any]:
    """分页拉取 ERP 产品列表，写入本地 erp_products 表。"""
    db: Session = SessionLocal()
    try:
        ensure_tables(db)
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        synced = 0
        failed = 0
        page = 1
        rows_per_page = 200

        while True:
            product_list = await erp_list_products(erp_client, page=page, rows=rows_per_page)
            for item in product_list.rows:
                try:
                    await run_in_threadpool(_upsert_product, db, item, now_str)
                    synced += 1
                except Exception as exc:
                    logger.warning("[ERP Sync] 同步产品 %s 失败: %s", item.product_id, exc)
                    failed += 1
                    try:
                        db.rollback()
                    except Exception:
                        pass
            await asyncio.sleep(0)  # 让出事件循环

            if page * rows_per_page >= product_list.total:
                break
            page += 1

        result = {
            "total_found": synced + failed,
            "synced": synced,
            "failed": failed,
            "synced_at": now_str,
        }
        logger.info("[ERP Sync] 产品同步完成: %s", result)
        return result

    except Exception:
        logger.exception("[ERP Sync] 产品同步异常")
        raise
    finally:
        db.close()


def _upsert_product(db: Session, item: Any, synced_at: str) -> None:
    """插入或更新一条产品记录"""
    existing = db.execute(
        text("SELECT id FROM erp_products WHERE product_id = :pid"),
        {"pid": item.product_id},
    ).mappings().first()

    data = {
        "product_id": item.product_id,
        "product_no": item.product_no or "",
        "product_name": item.product_name or "",
        "brand": item.brand or "",
        "category": item.category or "",
        "color": item.color or "",
        "unit": item.unit or "",
        "price": item.price or 0,
        "spec": item.spec or "",
        "material": item.material or "",
        "image_url": item.image_url or "",
        "remark": item.remark or "",
        "synced_at": synced_at,
    }

    if existing:
        sets = ", ".join(f"{k} = :{k}" for k in data if k != "product_id")
        data["_id"] = existing["id"]
        db.execute(text(f"UPDATE erp_products SET {sets} WHERE id = :_id"), data)
    else:
        cols = ", ".join(data.keys())
        vals = ", ".join(f":{k}" for k in data.keys())
        db.execute(text(f"INSERT INTO erp_products ({cols}) VALUES ({vals})"), data)
    db.commit()


# ---------------------------------------------------------------------------
# 库存同步
# ---------------------------------------------------------------------------

async def sync_inventory(erp_client: ERPClient) -> dict[str, Any]:
    """分页拉取 ERP 库存数据，写入本地 erp_inventory 表。"""
    db: Session = SessionLocal()
    try:
        ensure_tables(db)
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        synced = 0
        failed = 0
        page = 1
        rows_per_page = 500

        while True:
            inv_resp = await erp_query_inventory(
                erp_client,
                warehouse=None,
                product_type=None,
                product_no=None,
                product_name=None,
                show_zero=False,
                show_negative=True,
                page=page,
                rows=rows_per_page,
            )
            for item in inv_resp.rows:
                try:
                    await run_in_threadpool(_upsert_inventory_item, db, item, now_str)
                    synced += 1
                except Exception as exc:
                    logger.warning("[ERP Sync] 同步库存 %s/%s 失败: %s", item.warehouse, item.product_no, exc)
                    failed += 1
                    try:
                        db.rollback()
                    except Exception:
                        pass
            await asyncio.sleep(0)  # 让出事件循环

            if page * rows_per_page >= inv_resp.total:
                break
            page += 1

        result = {
            "total_found": synced + failed,
            "synced": synced,
            "failed": failed,
            "synced_at": now_str,
        }
        logger.info("[ERP Sync] 库存同步完成: %s", result)
        return result

    except Exception:
        logger.exception("[ERP Sync] 库存同步异常")
        raise
    finally:
        db.close()


def _upsert_inventory_item(db: Session, item: Any, synced_at: str) -> None:
    """插入或更新一条库存记录，唯一键为 (warehouse, product_no, color)"""
    sizes_list = [{"size": s.size, "qty": s.qty} for s in item.sizes] if item.sizes else []

    data = {
        "warehouse": item.warehouse or "",
        "product_type": item.product_type or "",
        "product_no": item.product_no or "",
        "product_name": item.product_name or "",
        "material": item.material or "",
        "image_url": item.image_url or "",
        "color": item.color or "",
        "unit": item.unit or "",
        "qty": item.qty or 0,
        "sale_price": item.sale_price or 0,
        "cost_price": item.cost_price or 0,
        "amount": item.amount or 0,
        "in_transit_qty": item.in_transit_qty or 0,
        "sizes_json": json.dumps(sizes_list, ensure_ascii=False) if sizes_list else "[]",
        "synced_at": synced_at,
    }

    existing = db.execute(
        text("SELECT id FROM erp_inventory WHERE warehouse = :warehouse AND product_no = :product_no AND color = :color"),
        {"warehouse": data["warehouse"], "product_no": data["product_no"], "color": data["color"]},
    ).mappings().first()

    if existing:
        sets = ", ".join(f"{k} = :{k}" for k in data if k not in ("warehouse", "product_no", "color"))
        data["_id"] = existing["id"]
        db.execute(text(f"UPDATE erp_inventory SET {sets} WHERE id = :_id"), data)
    else:
        cols = ", ".join(data.keys())
        vals = ", ".join(f":{k}" for k in data.keys())
        db.execute(text(f"INSERT INTO erp_inventory ({cols}) VALUES ({vals})"), data)
    db.commit()


# ---------------------------------------------------------------------------
# 单订单 & 按款号库存 — 审核操作后的精准同步
# ---------------------------------------------------------------------------

async def sync_single_order(erp_client: ERPClient, order_no: str) -> dict[str, Any]:
    """拉取单张销售订单详情并写入本地数据库。"""
    if not order_no:
        return {"synced": 0, "message": "无订单号"}
    db: Session = SessionLocal()
    try:
        ensure_tables(db)
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        detail = await get_order_detail(erp_client, order_no)
        await run_in_threadpool(_upsert_order, db, detail, now_str)
        logger.info("[ReviewSync] 单订单 %s 同步成功", order_no)
        return {"synced": 1, "order_no": order_no}
    except Exception as exc:
        logger.exception("[ReviewSync] 单订单 %s 同步失败", order_no)
        return {"synced": 0, "order_no": order_no, "error": str(exc)}
    finally:
        db.close()


async def sync_inventory_by_product_nos(erp_client: ERPClient, product_nos: list[str]) -> dict[str, Any]:
    """按款号列表逐个查询 ERP 库存并写入本地数据库。"""
    if not product_nos:
        return {"synced": 0, "message": "无款号"}
    db: Session = SessionLocal()
    try:
        ensure_tables(db)
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        synced = 0
        failed = 0
        for pno in product_nos:
            try:
                inv_resp = await erp_query_inventory(
                    erp_client,
                    warehouse=None,
                    product_type=None,
                    product_no=pno,
                    product_name=None,
                    show_zero=False,
                    show_negative=True,
                    page=1,
                    rows=500,
                )
                for item in inv_resp.rows:
                    await run_in_threadpool(_upsert_inventory_item, db, item, now_str)
                    synced += 1
            except Exception:
                logger.warning("[ReviewSync] 库存同步款号 %s 失败", pno, exc_info=True)
                failed += 1
                try:
                    db.rollback()
                except Exception:
                    pass
        result = {"synced": synced, "failed": failed, "product_nos": product_nos}
        logger.info("[ReviewSync] 库存按款号同步完成: %s", result)
        return result
    except Exception:
        logger.exception("[ReviewSync] 库存按款号同步异常")
        raise
    finally:
        db.close()


# ---------------------------------------------------------------------------
# 未发货报表同步
# ---------------------------------------------------------------------------

async def sync_unshipped_report(erp_client: ERPClient, days_back: int | None = None) -> dict[str, Any]:
    """
    拉取 ERP 未发货报表，写入本地 erp_unshipped_report 表。
    使用滑动时间窗口向前回溯，直到某个窗口返回 0 条记录时停止。
    返回同步统计信息。
    """
    cfg = _get_db_config()
    window_days = days_back or cfg.get("sync_days_back", 360)
    # 短周期（<=180天，即定时同步）：找到数据就停，空窗口顺延
    # 长周期（>180天，即手动同步）：完整滑动窗口回溯
    stop_on_data = window_days <= 180

    db: Session = SessionLocal()
    try:
        ensure_tables(db)
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # 1. 使用滑动窗口获取所有未发货数据
        all_items: list = []
        window_end = datetime.now()
        total_windows = 0
        consecutive_empty = 0

        while True:
            datee = window_end.strftime("%Y-%m-%d")
            dates = (window_end - timedelta(days=window_days)).strftime("%Y-%m-%d")
            total_windows += 1

            window_count = 0
            page = 1
            rows_per_page = 500
            while True:
                try:
                    report = await erp_query_unshipped(
                        erp_client,
                        dates=dates,
                        datee=datee,
                        customer_id=None,
                        brand=None,
                        product_no=None,
                        page=page,
                        rows=rows_per_page,
                    )
                except Exception as exc:
                    logger.warning("[ERP Sync] 未发货报表窗口 %s~%s 第 %d 页失败: %s", dates, datee, page, exc)
                    break

                for item in report.rows:
                    all_items.append(item)
                    window_count += 1

                if page * rows_per_page >= report.total:
                    break
                page += 1

            logger.info("[ERP Sync] 未发货报表窗口 %s ~ %s 获取 %d 条", dates, datee, window_count)

            if window_count > 0 and stop_on_data:
                break  # 定时同步：找到数据就停，不继续滑动

            if window_count == 0:
                consecutive_empty += 1
                if consecutive_empty >= 3:
                    break
            else:
                consecutive_empty = 0

            window_end = window_end - timedelta(days=window_days) - timedelta(days=1)

        logger.info("[ERP Sync] 获取到 %d 条未发货记录（共 %d 个窗口）", len(all_items), total_windows)

        # 2. 写入数据库
        synced = 0
        failed = 0

        for item in all_items:
            try:
                await run_in_threadpool(_upsert_unshipped_row, db, item, now_str)
                synced += 1
            except Exception as exc:
                logger.warning("[ERP Sync] 同步未发货行 %s 失败: %s", item.id, exc)
                failed += 1
                try:
                    db.rollback()
                except Exception:
                    pass

        # 3. 删除本次未更新的旧数据（已发货/已取消的行）
        try:
            db.execute(
                text("DELETE FROM erp_unshipped_report WHERE synced_at < :now"),
                {"now": now_str},
            )
            db.commit()
        except Exception:
            logger.warning("[ERP Sync] 清理旧未发货数据失败", exc_info=True)

        result = {
            "total_windows": total_windows,
            "total_found": len(all_items),
            "synced": synced,
            "failed": failed,
            "synced_at": now_str,
        }
        logger.info("[ERP Sync] 未发货报表同步完成: %s", result)
        return result

    except Exception:
        logger.exception("[ERP Sync] 未发货报表同步异常")
        raise
    finally:
        db.close()


def _upsert_unshipped_row(db: Session, item: Any, synced_at: str) -> None:
    """插入或更新一条未发货报表行，唯一键为 erp_row_id"""
    unshipped_sizes = [{"size": s.size, "qty": s.qty} for s in item.unshipped_sizes] if item.unshipped_sizes else []
    order_sizes = [{"size": s.size, "qty": s.qty} for s in item.order_sizes] if item.order_sizes else []

    data = {
        "erp_row_id": item.id or "",
        "order_no": item.order_no or "",
        "order_date": item.order_date or "",
        "customer_id": item.customer_id or "",
        "customer_type": item.customer_type or "",
        "customer_order_no": item.customer_order_no or "",
        "brand": item.brand or "",
        "product_no": item.product_no or "",
        "product_name": item.product_name or "",
        "color": item.color or "",
        "unit": item.unit or "",
        "order_qty": item.order_qty or 0,
        "shipped_qty": item.shipped_qty or 0,
        "returned_qty": item.returned_qty or 0,
        "unshipped_qty": item.unshipped_qty or 0,
        "unshipped_amount": item.unshipped_amount or 0,
        "stock_qty": item.stock_qty or 0,
        "price": item.price or 0,
        "cost_price": item.cost_price or 0,
        "tag_price": item.tag_price or 0,
        "creator": item.creator or "",
        "remark": item.remark or "",
        "unshipped_sizes_json": json.dumps(unshipped_sizes, ensure_ascii=False) if unshipped_sizes else "[]",
        "order_sizes_json": json.dumps(order_sizes, ensure_ascii=False) if order_sizes else "[]",
        "synced_at": synced_at,
    }

    existing = db.execute(
        text("SELECT id FROM erp_unshipped_report WHERE erp_row_id = :erp_row_id"),
        {"erp_row_id": data["erp_row_id"]},
    ).mappings().first()

    if existing:
        sets = ", ".join(f"{k} = :{k}" for k in data if k != "erp_row_id")
        data["_id"] = existing["id"]
        db.execute(text(f"UPDATE erp_unshipped_report SET {sets} WHERE id = :_id"), data)
    else:
        cols = ", ".join(data.keys())
        vals = ", ".join(f":{k}" for k in data.keys())
        db.execute(text(f"INSERT INTO erp_unshipped_report ({cols}) VALUES ({vals})"), data)
    db.commit()


# ---------------------------------------------------------------------------
# 定时调度器
# ---------------------------------------------------------------------------

_sync_task: Optional[asyncio.Task] = None
_last_sync_result: dict[str, Any] = {}
_is_syncing: bool = False
# ---------------------------------------------------------------------------
# 模块级同步锁 — 跨用户互斥
# ---------------------------------------------------------------------------
_module_syncing: dict[str, bool] = {
    "orders": False,
    "shipments": False,
    "products": False,
    "inventory": False,
    "unshipped": False,
}
# 记录每个模块当前同步的触发方式："scheduled"(定时) / "manual"(手动) / ""
_sync_trigger: dict[str, str] = {
    "orders": "",
    "shipments": "",
    "products": "",
    "inventory": "",
    "unshipped": "",
}


def is_module_syncing(module: str) -> bool:
    return _module_syncing.get(module, False)


def get_all_module_sync_status() -> dict[str, Any]:
    return {k: {"syncing": v, "trigger": _sync_trigger.get(k, "")} for k, v in _module_syncing.items()}


async def _sync_module(module: str, coro, trigger: str = "manual"):
    """带模块锁的同步包装器，完成后广播通知前端"""
    from app.services import ws_notify

    if _module_syncing.get(module, False):
        return None  # 已在同步中
    _module_syncing[module] = True
    _sync_trigger[module] = trigger
    try:
        result = await coro
        await ws_notify.broadcast("sync_complete", {"module": module, "success": True, "trigger": trigger})
        return result
    except Exception:
        await ws_notify.broadcast("sync_complete", {"module": module, "success": False, "trigger": trigger})
        raise
    finally:
        _module_syncing[module] = False
        _sync_trigger[module] = ""


def _record_sync_cycle_message(cycle_result: dict[str, Any], trigger: str = "定时") -> None:
    """将一次同步周期的所有模块结果汇总为一条系统消息和一条系统动态"""
    now = datetime.now()
    _MODULE_LABELS = {
        "orders": "销售订单",
        "shipments": "销售发货单",
        "products": "产品",
        "inventory": "库存",
        "unshipped": "未发货报表",
    }

    lines: list[str] = []
    has_error = False
    for key, label in _MODULE_LABELS.items():
        r = cycle_result.get(key)
        if r is None or (isinstance(r, dict) and r.get("skipped")):
            lines.append(f"  {label}：跳过")
            continue
        if isinstance(r, dict) and "error" in r:
            has_error = True
            lines.append(f"  {label}：失败 - {str(r['error'])[:80]}")
            continue
        if isinstance(r, dict):
            total = r.get("total_found", 0)
            synced = r.get("synced", 0)
            failed = r.get("failed", 0)
            line = f"  {label}：发现 {total}，成功 {synced}"
            if failed:
                line += f"，失败 {failed}"
                has_error = True
            lines.append(line)
        else:
            lines.append(f"  {label}：完成")

    summary = "\n".join(lines)
    level = "error" if has_error else "success"
    msg_type = "urgent" if has_error else "info"
    status_text = "部分失败" if has_error else "全部完成"
    title = f"【{trigger}】ERP 同步{status_text}"

    try:
        create_activity_background(
            title=title,
            content=f"【{trigger}】ERP 同步于 {now.strftime('%H:%M:%S')} {status_text}：\n{summary}",
            type=msg_type,
            source="erp_sync",
        )
        create_system_message_background(
            title=title,
            content=f"【{trigger}】ERP 同步于 {now.strftime('%H:%M:%S')} {status_text}：\n{summary}",
            level=level,
            source="erp_sync",
        )
    except Exception:
        logger.exception("[ERP Sync] 写入同步汇总记录失败")


async def _sync_loop(erp_client: ERPClient) -> None:
    """后台循环，每隔 N 分钟执行一次同步"""
    global _last_sync_result, _is_syncing

    _MAX_MODULE_RETRIES = 2  # 每个模块最多额外重试 2 次
    _RETRY_DELAY = 5         # 重试前等待秒数

    async def _run_module_with_retry(module_key: str, coro_factory, label: str, trigger: str = "scheduled") -> dict[str, Any] | None:
        """执行单模块同步，失败时重试（含重新登录）"""
        last_exc: Exception | None = None
        for attempt in range(_MAX_MODULE_RETRIES + 1):
            try:
                result = await _sync_module(module_key, coro_factory(), trigger=trigger)
                return result
            except Exception as exc:
                last_exc = exc
                if attempt < _MAX_MODULE_RETRIES:
                    logger.warning("[ERP Sync] %s 同步失败 (第%d次)，%d秒后重试: %s",
                                   label, attempt + 1, _RETRY_DELAY, exc)
                    # 可能是 session 过期，强制重新登录
                    try:
                        erp_client._auth.invalidate()
                    except Exception:
                        pass
                    await asyncio.sleep(_RETRY_DELAY)
                else:
                    logger.exception("[ERP Sync] %s 同步异常（已重试%d次）", label, _MAX_MODULE_RETRIES)
        return {"error": str(last_exc)}

    # 启动后先等 10 秒再执行第一次，给服务初始化时间
    await asyncio.sleep(10)

    while True:
        cfg = _get_db_config()
        interval = int(cfg.get("sync_interval_minutes", 15)) * 60
        cycle_result: dict[str, Any] = {}
        cycle_start = datetime.now()
        logger.info("[ERP Sync] ===== 定时同步周期开始 =====")
        try:
            _is_syncing = True
            # 定时同步采用增量模式：只拉最近 30 天的数据，
            # 30天之前的历史数据保持不变，仅通过手动全量同步更新。
            _SCHEDULED_DAYS_BACK = 30

            # 4 个模块并发执行，各自写不同的表，互不冲突
            r_orders, r_shipments, r_products, r_inventory, r_unshipped = await asyncio.gather(
                _run_module_with_retry(
                    "orders", lambda: sync_sales_orders(erp_client, days_back=_SCHEDULED_DAYS_BACK), "销售订单"),
                _run_module_with_retry(
                    "shipments", lambda: sync_sales_shipments(erp_client, days_back=_SCHEDULED_DAYS_BACK), "发货单"),
                _run_module_with_retry(
                    "products", lambda: sync_products(erp_client), "产品"),
                _run_module_with_retry(
                    "inventory", lambda: sync_inventory(erp_client), "库存"),
                _run_module_with_retry(
                    "unshipped", lambda: sync_unshipped_report(erp_client, days_back=_SCHEDULED_DAYS_BACK), "未发货报表"),
            )
            cycle_result["orders"] = r_orders or {"skipped": True}
            cycle_result["shipments"] = r_shipments or {"skipped": True}
            cycle_result["products"] = r_products or {"skipped": True}
            cycle_result["inventory"] = r_inventory or {"skipped": True}
            cycle_result["unshipped"] = r_unshipped or {"skipped": True}

            cycle_result["synced_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            _last_sync_result = cycle_result
        except Exception as loop_exc:
            logger.exception("[ERP Sync] 同步周期异常: %s", loop_exc)
        finally:
            _is_syncing = False
            elapsed = (datetime.now() - cycle_start).total_seconds()
            logger.info("[ERP Sync] ===== 定时同步周期结束，耗时 %.1f 秒，下次 %d 分钟后 =====", elapsed, interval // 60)
            # 无论成功失败，都汇总为一条系统消息和动态
            try:
                _record_sync_cycle_message(cycle_result, trigger="定时")
            except Exception:
                logger.exception("[ERP Sync] 写入同步汇总消息失败")

        await asyncio.sleep(interval)


def start_sync_scheduler(erp_client: ERPClient) -> None:
    """启动定时同步后台任务（首次启动用，后续用 restart_sync_scheduler）"""
    global _sync_task
    if _sync_task is not None and not _sync_task.done():
        logger.warning("[ERP Sync] 调度器已在运行中")
        return
    try:
        cfg = _get_db_config()
    except Exception:
        cfg = {}
    if not cfg.get("erp_base_url") and not settings.ERP_BASE_URL:
        logger.info("[ERP Sync] 未配置 ERP 地址，跳过自动同步")
        return
    if not cfg.get("sync_enabled", True):
        logger.info("[ERP Sync] 同步已禁用")
        return
    _sync_task = asyncio.create_task(_sync_loop(erp_client))
    logger.info("[ERP Sync] 定时同步已启动，间隔 %s 分钟", cfg.get("sync_interval_minutes", 15))


def get_sync_status() -> dict[str, Any]:
    """获取同步状态"""
    try:
        cfg = _get_db_config()
    except Exception:
        cfg = {}
    return {
        "is_syncing": _is_syncing,
        "interval_minutes": cfg.get("sync_interval_minutes", settings.ERP_SYNC_INTERVAL_MINUTES),
        "days_back": cfg.get("sync_days_back", settings.ERP_SYNC_DAYS_BACK),
        "sync_enabled": cfg.get("sync_enabled", True),
        "scheduler_running": _sync_task is not None and not _sync_task.done() if _sync_task else False,
        "last_result": _last_sync_result,
    }
