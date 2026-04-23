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
from app.database import SessionLocal
from app.ncloud.client.erp_client import ERPClient
from app.ncloud.services.sales_orders import get_order_detail, list_orders

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
    INDEX idx_product_no (product_no)
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
    "sync_days_back": "90",
    "sync_enabled": "true",
}


def ensure_tables(db: Session) -> None:
    """确保同步表存在"""
    db.execute(text(_DDL_ORDERS))
    db.execute(text(_DDL_ITEMS))
    db.execute(text(_DDL_SYNC_CONFIG))
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
    cfg["sync_days_back"] = int(cfg.get("sync_days_back") or 90)
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
    返回同步统计信息。
    """
    cfg = _get_db_config()
    days = days_back or cfg.get("sync_days_back", 90)
    datee = datetime.now().strftime("%Y-%m-%d")
    dates = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")

    db: Session = SessionLocal()
    try:
        ensure_tables(db)

        # 1. 获取销售订单列表（分页拉取全部）
        all_order_nos: list[str] = []
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
                all_order_nos.append(item.order_no)
            if page * rows_per_page >= order_list.total:
                break
            page += 1

        logger.info("[ERP Sync] 获取到 %d 张销售订单（%s ~ %s）", len(all_order_nos), dates, datee)

        synced = 0
        failed = 0
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # 2. 逐单获取详情并写入数据库
        for order_no in all_order_nos:
            try:
                detail = await get_order_detail(erp_client, order_no)
                _upsert_order(db, detail, now_str)
                synced += 1
            except Exception as exc:
                logger.warning("[ERP Sync] 同步订单 %s 失败: %s", order_no, exc)
                failed += 1
                try:
                    db.rollback()
                except Exception:
                    pass

        result = {
            "dates": dates,
            "datee": datee,
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


def _upsert_order(db: Session, detail: Any, synced_at: str) -> None:
    """插入或更新一张订单（主表 + 明细行）"""
    main = detail.main
    order_no = main.order_no

    # upsert 主表
    existing = db.execute(
        text("SELECT id FROM erp_sales_orders WHERE order_no = :order_no"),
        {"order_no": order_no},
    ).mappings().first()

    order_data = {
        "order_no": order_no,
        "order_date": main.order_date or "",
        "state": main.state,
        "customer_id": main.customer_id or "",
        "customer_name": main.customer_name or "",
        "customer_tel": main.customer_tel or "",
        "customer_addr": main.customer_addr or "",
        "salesperson": main.salesperson or "",
        "creator": main.creator or "",
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
# 定时调度器
# ---------------------------------------------------------------------------

_sync_task: Optional[asyncio.Task] = None
_last_sync_result: dict[str, Any] = {}
_is_syncing: bool = False


async def _sync_loop(erp_client: ERPClient) -> None:
    """后台循环，每隔 N 分钟执行一次同步"""
    global _last_sync_result, _is_syncing

    # 启动后先等 10 秒再执行第一次，给服务初始化时间
    await asyncio.sleep(10)

    while True:
        cfg = _get_db_config()
        try:
            _is_syncing = True
            _last_sync_result = await sync_sales_orders(erp_client)
        except Exception as exc:
            _last_sync_result = {"error": str(exc), "synced_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
        finally:
            _is_syncing = False

        interval = int(cfg.get("sync_interval_minutes", 15)) * 60
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
