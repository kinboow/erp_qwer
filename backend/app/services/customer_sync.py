"""
ERP 客户同步服务 — 从弘兆云 ERP 拉取客户列表并写入 downstream_customers 表。
通过 erp_customer_id 做 upsert，保留本地手工维护的 wechat_rooms 等关联数据。
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.ncloud.client.erp_client import ERPClient
from app.ncloud.services.base import list_customers
from app.services.downstream_support import ensure_downstream_support_tables

logger = logging.getLogger(__name__)


async def sync_customers(erp_client: ERPClient) -> dict[str, Any]:
    """
    分页拉取 ERP 全量客户列表，upsert 到 downstream_customers 表。
    匹配规则：erp_customer_id = ERP bh（客户编号）
    """
    db: Session = SessionLocal()
    try:
        ensure_downstream_support_tables(db)

        # 1. 分页拉取全部客户
        all_customers = []
        page = 1
        rows_per_page = 500
        while True:
            result = await list_customers(erp_client, page=page, rows=rows_per_page)
            all_customers.extend(result.rows)
            if page * rows_per_page >= result.total:
                break
            page += 1

        logger.info("[Customer Sync] 获取到 %d 个 ERP 客户", len(all_customers))

        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        synced = 0
        skipped = 0

        # 2. 逐个 upsert
        for cust in all_customers:
            erp_id = cust.customer_id
            if not erp_id:
                skipped += 1
                continue

            try:
                existing = db.execute(
                    text("SELECT id FROM downstream_customers WHERE erp_customer_id = :eid AND deleted_at IS NULL"),
                    {"eid": erp_id},
                ).mappings().first()

                data = {
                    "customer_name": cust.customer_name or "",
                    "contact_person": cust.contact_person or "",
                    "phone": cust.phone or "",
                    "telephone": cust.telephone or "",
                    "company_name": "",
                    "address": cust.address or "",
                    "remark": cust.remark or "",
                    "erp_customer_id": erp_id,
                    "status": 1 if (cust.state is None or cust.state == 0) else 0,
                    "salesperson": cust.salesperson or "",
                    "customer_type": cust.customer_type or "",
                    "shipping_address": cust.shipping_address or "",
                    "shipping_phone": cust.shipping_phone or "",
                    "short_code": cust.short_code or "",
                    "nature": json.dumps(cust.nature, ensure_ascii=False) if cust.nature else "",
                    "credit_limit": cust.credit_limit,
                    "synced_at": now_str,
                }

                if existing:
                    set_clause = ", ".join(f"{k} = :{k}" for k in data)
                    data["_id"] = existing["id"]
                    db.execute(
                        text(f"UPDATE downstream_customers SET {set_clause} WHERE id = :_id"),
                        data,
                    )
                else:
                    cols = ", ".join(data.keys())
                    vals = ", ".join(f":{k}" for k in data.keys())
                    db.execute(
                        text(f"INSERT INTO downstream_customers ({cols}) VALUES ({vals})"),
                        data,
                    )
                synced += 1
            except Exception as exc:
                logger.warning("[Customer Sync] 同步客户 %s 失败: %s", erp_id, exc)
                try:
                    db.rollback()
                except Exception:
                    pass

        db.commit()
        result = {
            "total_found": len(all_customers),
            "synced": synced,
            "skipped": skipped,
            "synced_at": now_str,
        }
        logger.info("[Customer Sync] 同步完成: %s", result)
        return result

    except Exception:
        logger.exception("[Customer Sync] 同步异常")
        raise
    finally:
        db.close()
