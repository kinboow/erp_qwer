"""待发货报表 — 从本地数据库读取已同步的未发货报表数据"""

from __future__ import annotations

import json
from typing import Any, Optional

from fastapi import APIRouter, Body, Depends, Query
from pydantic import BaseModel
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
        conditions.append("u.order_date >= :dates")
        params["dates"] = dates
    if datee:
        conditions.append("u.order_date <= :datee")
        params["datee"] = datee
    if customer_id:
        conditions.append("u.customer_id = :customer_id")
        params["customer_id"] = customer_id
    if brand:
        conditions.append("u.brand = :brand")
        params["brand"] = brand
    if product_no:
        conditions.append("u.product_no LIKE :product_no")
        params["product_no"] = f"%{product_no}%"
    if order_no:
        conditions.append("u.order_no LIKE :order_no")
        params["order_no"] = f"%{order_no}%"
    if keyword:
        conditions.append(
            "(u.order_no LIKE :keyword OR u.product_no LIKE :keyword "
            "OR u.product_name LIKE :keyword OR u.customer_id LIKE :keyword "
            "OR u.color LIKE :keyword)"
        )
        params["keyword"] = f"%{keyword}%"

    where_sql = " AND ".join(conditions)
    count_params = {k: v for k, v in params.items() if k not in ("limit", "offset")}

    # 总数 + 汇总统计 合并为一条查询
    agg = db.execute(
        text(
            f"SELECT COUNT(*) AS total, "
            f"COALESCE(SUM(u.order_qty), 0) AS total_order_qty, "
            f"COALESCE(SUM(u.shipped_qty), 0) AS total_shipped_qty, "
            f"COALESCE(SUM(u.unshipped_qty), 0) AS total_unshipped_qty, "
            f"COALESCE(SUM(u.unshipped_amount), 0) AS total_unshipped_amount "
            f"FROM erp_unshipped_report u WHERE {where_sql}"
        ),
        count_params,
    ).mappings().first()

    total = agg["total"]
    summary = {
        "total_order_qty": agg["total_order_qty"],
        "total_shipped_qty": agg["total_shipped_qty"],
        "total_unshipped_qty": agg["total_unshipped_qty"],
        "total_unshipped_amount": agg["total_unshipped_amount"],
    }

    # 数据 — LEFT JOIN 销售订单表获取客户名称
    rows = db.execute(
        text(
            f"SELECT u.id, u.order_no, u.order_date, u.customer_id, "
            f"COALESCE(o.customer_name, u.customer_id) AS customer_name, "
            f"u.product_no, u.color, "
            f"u.order_qty, u.unshipped_qty, u.remark, "
            f"u.unshipped_sizes_json "
            f"FROM erp_unshipped_report u "
            f"LEFT JOIN erp_sales_orders o ON u.order_no = o.order_no "
            f"WHERE {where_sql} "
            f"ORDER BY u.order_date DESC, u.order_no ASC, u.product_no ASC "
            f"LIMIT :limit OFFSET :offset"
        ),
        params,
    ).mappings().all()

    result = []
    for row in rows:
        item = dict(row)
        raw = item.pop("unshipped_sizes_json", None) or "[]"
        try:
            item["unshipped_sizes"] = json.loads(raw)
        except Exception:
            item["unshipped_sizes"] = []
        result.append(item)

    return json_response(data={
        "list": result,
        "total": total,
        "summary": summary,
    })


@router.get("/{row_id}", summary="获取单条未发货记录详情")
def api_get_unshipped_detail(
    row_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    ensure_tables(db)
    row = db.execute(
        text(
            "SELECT id, erp_row_id, order_no, order_date, customer_id, customer_type, "
            "customer_order_no, brand, product_no, product_name, color, unit, "
            "order_qty, shipped_qty, returned_qty, unshipped_qty, unshipped_amount, "
            "stock_qty, price, cost_price, tag_price, creator, remark, "
            "unshipped_sizes_json, order_sizes_json, synced_at "
            "FROM erp_unshipped_report WHERE id = :row_id"
        ),
        {"row_id": row_id},
    ).mappings().first()

    if not row:
        return json_response(code=404, message="记录不存在")

    item = dict(row)
    for json_field, out_field in [
        ("unshipped_sizes_json", "unshipped_sizes"),
        ("order_sizes_json", "order_sizes"),
    ]:
        raw = item.pop(json_field, None) or "[]"
        try:
            item[out_field] = json.loads(raw)
        except Exception:
            item[out_field] = []

    return json_response(data=item)


class PrintUnshippedRequest(BaseModel):
    ids: list[int]
    customer_name: str = ""
    print_mode: str = "local"  # local=本地打印, remote=远程打印


@router.post("/print", summary="生成待发货单 PDF")
def api_print_unshipped(
    req: PrintUnshippedRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    from app.services.unshipped_print import generate_unshipped_pdf
    try:
        result = generate_unshipped_pdf(db, req.ids, req.customer_name)
        if req.print_mode == "remote":
            from app.services.printer_service import enqueue_existing_pdf
            oss_url = result.get("oss_url", "")
            # 从 oss_url 提取 object_name: /api/sales-orders/oss-file/unshipped/xxx.pdf?t=...
            object_name = oss_url.split("/oss-file/")[-1].split("?")[0] if "/oss-file/" in oss_url else ""
            first_order = req.ids[0] if req.ids else 0
            enqueue_existing_pdf(db, str(first_order), doc_type="unshipped", pdf_object=object_name)
            result["remote_queued"] = True
        return json_response(data=result)
    except ValueError as e:
        return json_response(code=404, message=str(e))
    except Exception as e:
        import logging
        logging.getLogger(__name__).exception("待发货单打印失败: %s", e)
        return json_response(code=500, message=f"生成待发货单失败: {str(e)}")


@router.get("/print-history/{order_no}", summary="查询待发货单打印历史")
def api_unshipped_print_history(
    order_no: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """返回该订单所有待发货打印页面记录（含已废除），按创建时间降序"""
    from app.services.unshipped_print import ensure_print_tables
    ensure_print_tables(db)
    rows = db.execute(
        text(
            "SELECT page_id, page_index, barcode_content, status, created_at "
            "FROM unshipped_print_pages WHERE order_no = :no "
            "ORDER BY created_at DESC, id DESC"
        ),
        {"no": order_no},
    ).mappings().all()
    return json_response(data=[dict(r) for r in rows])
