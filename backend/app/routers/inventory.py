"""库存查询 — 从本地数据库读取已同步的库存数据"""

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

router = APIRouter(prefix="/inventory", tags=["库存查询"])


def json_response(code=200, message="success", data=None):
    resp = {"code": code, "message": message}
    if data is not None:
        resp["data"] = data
    return resp


@router.get("", summary="查询库存列表")
def api_list_inventory(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
    warehouse: Optional[str] = Query(None),
    product_type: Optional[str] = Query(None),
    product_no: Optional[str] = Query(None),
    product_no_exact: Optional[str] = Query(None),
    product_name: Optional[str] = Query(None),
    keyword: Optional[str] = Query(None),
    show_zero: bool = Query(False),
    show_negative: bool = Query(False),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    ensure_tables(db)

    conditions = ["1 = 1"]
    params: dict[str, Any] = {"limit": page_size, "offset": (page - 1) * page_size}

    if not show_zero:
        conditions.append("qty != 0")
    if not show_negative:
        conditions.append("qty >= 0")
    if warehouse:
        conditions.append("warehouse = :warehouse")
        params["warehouse"] = warehouse
    if product_type:
        conditions.append("product_type = :product_type")
        params["product_type"] = product_type
    if product_no_exact:
        conditions.append("product_no = :product_no_exact")
        params["product_no_exact"] = product_no_exact
    elif product_no:
        conditions.append("product_no LIKE :product_no")
        params["product_no"] = f"%{product_no}%"
    if product_name:
        conditions.append("product_name LIKE :product_name")
        params["product_name"] = f"%{product_name}%"
    if keyword:
        conditions.append(
            "(product_no LIKE :keyword OR product_name LIKE :keyword "
            "OR warehouse LIKE :keyword OR color LIKE :keyword OR material LIKE :keyword)"
        )
        params["keyword"] = f"%{keyword}%"

    where_sql = " AND ".join(conditions)

    # 总数
    count_params = {k: v for k, v in params.items() if k not in ("limit", "offset")}
    total = db.execute(
        text(f"SELECT COUNT(*) AS total FROM erp_inventory WHERE {where_sql}"),
        count_params,
    ).mappings().first()["total"]

    # 数据
    rows = db.execute(
        text(
            f"SELECT id, warehouse, product_type, product_no, product_name, material, "
            f"image_url, color, unit, qty, sale_price, cost_price, amount, in_transit_qty, "
            f"sizes_json, synced_at "
            f"FROM erp_inventory WHERE {where_sql} "
            f"ORDER BY warehouse ASC, product_no ASC, color ASC "
            f"LIMIT :limit OFFSET :offset"
        ),
        params,
    ).mappings().all()

    result = []
    for row in rows:
        item = dict(row)
        # 解析尺码 JSON
        sizes_raw = item.pop("sizes_json", None) or "[]"
        try:
            item["sizes"] = json.loads(sizes_raw)
        except Exception:
            item["sizes"] = []
        result.append(item)

    return json_response(data={"list": result, "total": total})


@router.get("/grouped", summary="按货号分组查询库存")
def api_list_inventory_grouped(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
    warehouse: Optional[str] = Query(None),
    product_type: Optional[str] = Query(None),
    product_no: Optional[str] = Query(None),
    product_no_exact: Optional[str] = Query(None),
    product_name: Optional[str] = Query(None),
    keyword: Optional[str] = Query(None),
    show_zero: bool = Query(False),
    show_negative: bool = Query(False),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    ensure_tables(db)

    conditions = ["1 = 1"]
    params: dict[str, Any] = {}

    if not show_zero:
        conditions.append("qty != 0")
    if not show_negative:
        conditions.append("qty >= 0")
    if warehouse:
        conditions.append("warehouse = :warehouse")
        params["warehouse"] = warehouse
    if product_type:
        conditions.append("product_type = :product_type")
        params["product_type"] = product_type
    if product_no_exact:
        conditions.append("product_no = :product_no_exact")
        params["product_no_exact"] = product_no_exact
    elif product_no:
        conditions.append("product_no LIKE :product_no")
        params["product_no"] = f"%{product_no}%"
    if product_name:
        conditions.append("product_name LIKE :product_name")
        params["product_name"] = f"%{product_name}%"
    if keyword:
        conditions.append(
            "(product_no LIKE :keyword OR product_name LIKE :keyword "
            "OR warehouse LIKE :keyword OR color LIKE :keyword OR material LIKE :keyword)"
        )
        params["keyword"] = f"%{keyword}%"

    where_sql = " AND ".join(conditions)

    # 按货号分组统计总数
    total = db.execute(
        text(f"SELECT COUNT(DISTINCT product_no) AS total FROM erp_inventory WHERE {where_sql}"),
        params,
    ).mappings().first()["total"]

    # 分页获取货号列表
    paged_params = {**params, "limit": page_size, "offset": (page - 1) * page_size}
    product_nos_rows = db.execute(
        text(
            f"SELECT product_no FROM erp_inventory WHERE {where_sql} "
            f"GROUP BY product_no ORDER BY product_no ASC "
            f"LIMIT :limit OFFSET :offset"
        ),
        paged_params,
    ).mappings().all()
    product_nos = [r["product_no"] for r in product_nos_rows]

    if not product_nos:
        return json_response(data={"list": [], "total": total})

    # 查出这些货号的所有明细行
    placeholders = ", ".join([f":pn{i}" for i in range(len(product_nos))])
    detail_params = {f"pn{i}": pn for i, pn in enumerate(product_nos)}
    # 也要带上过滤条件（仓库 / 零库存等）
    detail_conditions = list(conditions)  # copy
    detail_conditions.append(f"product_no IN ({placeholders})")
    detail_where = " AND ".join(detail_conditions)
    detail_params.update(params)

    detail_rows = db.execute(
        text(
            f"SELECT product_no, product_name, product_type, material, image_url, "
            f"warehouse, color, unit, qty, sale_price, cost_price, amount, in_transit_qty, "
            f"sizes_json "
            f"FROM erp_inventory WHERE {detail_where} "
            f"ORDER BY product_no ASC, warehouse ASC, color ASC"
        ),
        detail_params,
    ).mappings().all()

    # 组装分组结果
    from collections import OrderedDict
    grouped: OrderedDict = OrderedDict()
    for pn in product_nos:
        grouped[pn] = {
            "product_no": pn,
            "product_name": "",
            "product_type": "",
            "material": "",
            "image_url": "",
            "unit": "",
            "total_qty": 0,
            "total_in_transit_qty": 0,
            "total_amount": 0,
            "color_count": 0,
            "colors": [],
        }

    for row in detail_rows:
        r = dict(row)
        pn = r["product_no"]
        g = grouped[pn]
        if not g["product_name"]:
            g["product_name"] = r["product_name"] or ""
            g["product_type"] = r["product_type"] or ""
            g["material"] = r["material"] or ""
            g["image_url"] = r["image_url"] or ""
            g["unit"] = r["unit"] or ""

        qty = r["qty"] or 0
        amount = r["amount"] or 0
        in_transit = r["in_transit_qty"] or 0
        g["total_qty"] += qty
        g["total_amount"] += amount
        g["total_in_transit_qty"] += in_transit

        sizes_raw = r.get("sizes_json") or "[]"
        try:
            sizes = json.loads(sizes_raw)
        except Exception:
            sizes = []

        g["colors"].append({
            "warehouse": r["warehouse"] or "",
            "color": r["color"] or "",
            "qty": qty,
            "in_transit_qty": in_transit,
            "sale_price": r["sale_price"] or 0,
            "cost_price": r["cost_price"] or 0,
            "amount": amount,
            "sizes": sizes,
        })

    for g in grouped.values():
        g["color_count"] = len(g["colors"])
        g["total_amount"] = round(g["total_amount"], 2)

    return json_response(data={"list": list(grouped.values()), "total": total})
