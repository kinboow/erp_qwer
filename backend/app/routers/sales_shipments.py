"""ERP 销售发货单查询 API — 本地数据库"""

from __future__ import annotations

import json
from typing import Any, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database import get_db
from app.services.erp_sync import ensure_tables

router = APIRouter(tags=["销售发货单"])


@router.get("/", summary="销售发货单列表（分页 + 筛选）")
def api_list_shipments(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    keyword: Optional[str] = Query(None, description="单号/客户名模糊搜索"),
    state: Optional[str] = Query(None, description="状态: 0=未审核, 1=已审核"),
    date_start: Optional[str] = Query(None, description="日期起"),
    date_end: Optional[str] = Query(None, description="日期止"),
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

    count_sql = f"SELECT COUNT(*) AS cnt FROM erp_sales_shipments WHERE {where}"
    total = db.execute(text(count_sql), params).scalar() or 0

    offset = (page - 1) * page_size
    data_sql = f"""
        SELECT id, order_no, order_date, state, customer_id, customer_name,
               customer_tel, customer_addr, salesperson, creator, handler,
               warehouse, shipping_method, shipping_tel, shipping_addr,
               tracking_no, delivery_person, contact_person, contact_tel,
               currency, customer_type, freight, payment_amount,
               total_qty, total_amount, remark, synced_at
        FROM erp_sales_shipments
        WHERE {where}
        ORDER BY order_date DESC, id DESC
        LIMIT :limit OFFSET :offset
    """
    params["limit"] = page_size
    params["offset"] = offset
    rows = db.execute(text(data_sql), params).mappings().all()

    shipments = []
    for r in rows:
        shipments.append({
            "id": r["id"],
            "order_no": r["order_no"],
            "order_date": r["order_date"] or "",
            "state": r["state"],
            "customer_id": r["customer_id"] or "",
            "customer_name": r["customer_name"] or "",
            "customer_tel": r["customer_tel"] or "",
            "customer_addr": r["customer_addr"] or "",
            "salesperson": r["salesperson"] or "",
            "creator": r["creator"] or "",
            "handler": r["handler"] or "",
            "warehouse": r["warehouse"] or "",
            "shipping_method": r["shipping_method"] or "",
            "shipping_tel": r["shipping_tel"] or "",
            "shipping_addr": r["shipping_addr"] or "",
            "tracking_no": r["tracking_no"] or "",
            "delivery_person": r["delivery_person"] or "",
            "contact_person": r["contact_person"] or "",
            "contact_tel": r["contact_tel"] or "",
            "currency": r["currency"] or "",
            "customer_type": r["customer_type"] or "",
            "freight": float(r["freight"]) if r["freight"] is not None else None,
            "payment_amount": float(r["payment_amount"]) if r["payment_amount"] is not None else None,
            "total_qty": float(r["total_qty"] or 0),
            "total_amount": float(r["total_amount"] or 0),
            "remark": r["remark"] or "",
            "synced_at": str(r["synced_at"] or ""),
        })

    return {
        "code": 200,
        "data": {
            "list": shipments,
            "total": total,
            "page": page,
            "page_size": page_size,
        },
    }


@router.get("/{order_no}", summary="销售发货单详情")
def api_shipment_detail(
    order_no: str,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    ensure_tables(db)
    row = db.execute(
        text("""
            SELECT id, order_no, order_date, state, customer_id, customer_name,
                   customer_tel, customer_addr, salesperson, creator, handler, warehouse,
                   shipping_method, shipping_tel, shipping_addr,
                   tracking_no, delivery_person, contact_person, contact_tel,
                   currency, customer_type, price_print, freight, payment_amount,
                   total_qty, total_amount, remark, synced_at
            FROM erp_sales_shipments
            WHERE order_no = :order_no
        """),
        {"order_no": order_no},
    ).mappings().first()

    if not row:
        return {"code": 404, "message": "发货单不存在", "data": None}

    shipment = {
        "id": row["id"],
        "order_no": row["order_no"],
        "order_date": row["order_date"] or "",
        "state": row["state"],
        "customer_id": row["customer_id"] or "",
        "customer_name": row["customer_name"] or "",
        "customer_tel": row["customer_tel"] or "",
        "customer_addr": row["customer_addr"] or "",
        "salesperson": row["salesperson"] or "",
        "creator": row["creator"] or "",
        "handler": row["handler"] or "",
        "warehouse": row["warehouse"] or "",
        "shipping_method": row["shipping_method"] or "",
        "shipping_tel": row["shipping_tel"] or "",
        "shipping_addr": row["shipping_addr"] or "",
        "tracking_no": row["tracking_no"] or "",
        "delivery_person": row["delivery_person"] or "",
        "contact_person": row["contact_person"] or "",
        "contact_tel": row["contact_tel"] or "",
        "currency": row["currency"] or "",
        "customer_type": row["customer_type"] or "",
        "price_print": row["price_print"],
        "freight": float(row["freight"]) if row["freight"] is not None else None,
        "payment_amount": float(row["payment_amount"]) if row["payment_amount"] is not None else None,
        "total_qty": float(row["total_qty"] or 0),
        "total_amount": float(row["total_amount"] or 0),
        "remark": row["remark"] or "",
        "synced_at": str(row["synced_at"] or ""),
    }
    return {"code": 200, "data": shipment}


@router.get("/{order_no}/items", summary="销售发货单明细行")
def api_shipment_items(
    order_no: str,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    ensure_tables(db)
    rows = db.execute(
        text("""
            SELECT sort_index, brand, product_no, product_name, color,
                   customer_product_no, packaging, unit, price, discount,
                   order_ref, sizes_json, total_qty, remark
            FROM erp_sales_shipment_items
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
            "customer_product_no": r["customer_product_no"] or "",
            "packaging": r["packaging"] or "",
            "unit": r["unit"] or "",
            "price": float(r["price"] or 0),
            "discount": r["discount"] or 100,
            "order_ref": r["order_ref"] or "",
            "sizes": sizes,
            "total_qty": float(r["total_qty"] or 0),
            "remark": r["remark"] or "",
        })

    return {"code": 200, "data": items}
