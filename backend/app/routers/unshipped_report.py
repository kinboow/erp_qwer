"""待发货报表 — 从本地数据库读取已同步的未发货报表数据"""

from __future__ import annotations

import json
from typing import Any, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.models import User
from app.services.erp_sync import ensure_tables

router = APIRouter(prefix="/unshipped-report", tags=["待发货报表"])


def json_response(code=200, message="success", data=None):
    resp = {"code": code, "message": message}
    if data is not None:
        resp["data"] = data
    return resp


@router.get("", summary="查询待发货报表")
def api_list_unshipped(
    page: int = Query(1, ge=1),
    page_size: int = Query(200, ge=1, le=1000),
    dates: Optional[str] = Query(None),
    datee: Optional[str] = Query(None),
    customer_id: Optional[str] = Query(None),
    brand: Optional[str] = Query(None),
    product_no: Optional[str] = Query(None),
    order_no: Optional[str] = Query(None),
    keyword: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    ensure_tables(db)

    conditions = ["1 = 1"]
    params: dict[str, Any] = {"limit": page_size, "offset": (page - 1) * page_size}

    if dates:
        conditions.append("order_date >= :dates")
        params["dates"] = dates
    if datee:
        conditions.append("order_date <= :datee")
        params["datee"] = datee
    if customer_id:
        conditions.append("customer_id = :customer_id")
        params["customer_id"] = customer_id
    if brand:
        conditions.append("brand = :brand")
        params["brand"] = brand
    if product_no:
        conditions.append("product_no LIKE :product_no")
        params["product_no"] = f"%{product_no}%"
    if order_no:
        conditions.append("order_no LIKE :order_no")
        params["order_no"] = f"%{order_no}%"
    if keyword:
        conditions.append(
            "(order_no LIKE :keyword OR product_no LIKE :keyword "
            "OR product_name LIKE :keyword OR customer_id LIKE :keyword "
            "OR color LIKE :keyword)"
        )
        params["keyword"] = f"%{keyword}%"

    where_sql = " AND ".join(conditions)

    # 总数
    count_params = {k: v for k, v in params.items() if k not in ("limit", "offset")}
    total = db.execute(
        text(f"SELECT COUNT(*) AS total FROM erp_unshipped_report WHERE {where_sql}"),
        count_params,
    ).mappings().first()["total"]

    # 数据
    rows = db.execute(
        text(
            f"SELECT id, erp_row_id, order_no, order_date, customer_id, customer_type, "
            f"customer_order_no, brand, product_no, product_name, color, unit, "
            f"order_qty, shipped_qty, returned_qty, unshipped_qty, unshipped_amount, "
            f"stock_qty, price, cost_price, tag_price, creator, remark, "
            f"unshipped_sizes_json, order_sizes_json, synced_at "
            f"FROM erp_unshipped_report WHERE {where_sql} "
            f"ORDER BY order_date DESC, order_no ASC, product_no ASC "
            f"LIMIT :limit OFFSET :offset"
        ),
        params,
    ).mappings().all()

    result = []
    for row in rows:
        item = dict(row)
        # 解析尺码 JSON
        for json_field, out_field in [
            ("unshipped_sizes_json", "unshipped_sizes"),
            ("order_sizes_json", "order_sizes"),
        ]:
            raw = item.pop(json_field, None) or "[]"
            try:
                item[out_field] = json.loads(raw)
            except Exception:
                item[out_field] = []
        result.append(item)

    # 汇总统计（当前筛选条件下）
    summary = db.execute(
        text(
            f"SELECT COALESCE(SUM(order_qty), 0) AS total_order_qty, "
            f"COALESCE(SUM(shipped_qty), 0) AS total_shipped_qty, "
            f"COALESCE(SUM(unshipped_qty), 0) AS total_unshipped_qty, "
            f"COALESCE(SUM(unshipped_amount), 0) AS total_unshipped_amount "
            f"FROM erp_unshipped_report WHERE {where_sql}"
        ),
        count_params,
    ).mappings().first()

    return json_response(data={
        "list": result,
        "total": total,
        "summary": dict(summary) if summary else {},
    })
