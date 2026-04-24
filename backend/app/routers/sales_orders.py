"""ERP 销售订单查询 API — 本地数据库"""

from __future__ import annotations

import json
from typing import Any, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database import get_db
from app.services.erp_sync import ensure_tables

router = APIRouter(tags=["销售订单"])


@router.get("/", summary="销售订单列表（分页 + 筛选）")
def api_list_orders(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    keyword: Optional[str] = Query(None, description="订单号/客户名模糊搜索"),
    state: Optional[str] = Query(None, description="订单状态: 0=未审核, 1=已审核"),
    date_start: Optional[str] = Query(None, description="下单日期起"),
    date_end: Optional[str] = Query(None, description="下单日期止"),
    salesperson: Optional[str] = Query(None, description="业务员"),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    ensure_tables(db)

    conditions = []
    params: dict[str, Any] = {}

    if keyword:
        conditions.append("(order_no LIKE :kw OR customer_name LIKE :kw)")
        params["kw"] = f"%{keyword}%"
    if state is not None and state != "":
        conditions.append("state = :state")
        params["state"] = int(state)
    if date_start:
        conditions.append("order_date >= :date_start")
        params["date_start"] = date_start
    if date_end:
        conditions.append("order_date <= :date_end")
        params["date_end"] = date_end
    if salesperson:
        conditions.append("salesperson LIKE :sp")
        params["sp"] = f"%{salesperson}%"

    where = " AND ".join(conditions) if conditions else "1=1"

    # 总数
    count_sql = f"SELECT COUNT(*) AS cnt FROM erp_sales_orders WHERE {where}"
    total = db.execute(text(count_sql), params).scalar() or 0

    # 分页查询
    offset = (page - 1) * page_size
    data_sql = f"""
        SELECT id, order_no, order_date, state, customer_name, customer_tel,
               salesperson, creator, delivery_date, shipping_method,
               currency, brand, customer_type, total_qty, total_amount,
               remark, synced_at
        FROM erp_sales_orders
        WHERE {where}
        ORDER BY order_date DESC, id DESC
        LIMIT :limit OFFSET :offset
    """
    params["limit"] = page_size
    params["offset"] = offset
    rows = db.execute(text(data_sql), params).mappings().all()

    orders = []
    for r in rows:
        orders.append({
            "id": r["id"],
            "order_no": r["order_no"],
            "order_date": r["order_date"] or "",
            "state": r["state"],
            "customer_name": r["customer_name"] or "",
            "customer_tel": r["customer_tel"] or "",
            "salesperson": r["salesperson"] or "",
            "creator": r["creator"] or "",
            "delivery_date": r["delivery_date"] or "",
            "shipping_method": r["shipping_method"] or "",
            "currency": r["currency"] or "",
            "brand": r["brand"] or "",
            "customer_type": r["customer_type"] or "",
            "total_qty": float(r["total_qty"] or 0),
            "total_amount": float(r["total_amount"] or 0),
            "remark": r["remark"] or "",
            "synced_at": str(r["synced_at"] or ""),
        })

    return {
        "code": 200,
        "data": {
            "list": orders,
            "total": total,
            "page": page,
            "page_size": page_size,
        },
    }


@router.get("/{order_no}/items", summary="销售订单明细行")
def api_order_items(
    order_no: str,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    ensure_tables(db)
    rows = db.execute(
        text("""
            SELECT sort_index, brand, product_no, product_name, color, grade,
                   customer_product_no, unit, price, discount, sizes_json,
                   total_qty, remark
            FROM erp_sales_order_items
            WHERE order_no = :order_no
            ORDER BY sort_index
        """),
        {"order_no": order_no},
    ).mappings().all()

    items = []
    for r in rows:
        sizes = []
        try:
            sizes = json.loads(r["sizes_json"] or "[]")
        except Exception:
            pass
        items.append({
            "sort_index": r["sort_index"],
            "brand": r["brand"] or "",
            "product_no": r["product_no"] or "",
            "product_name": r["product_name"] or "",
            "color": r["color"] or "",
            "grade": r["grade"] or "",
            "customer_product_no": r["customer_product_no"] or "",
            "unit": r["unit"] or "",
            "price": float(r["price"] or 0),
            "discount": r["discount"] or 100,
            "sizes": sizes,
            "total_qty": float(r["total_qty"] or 0),
            "remark": r["remark"] or "",
        })

    return {"code": 200, "data": items}
