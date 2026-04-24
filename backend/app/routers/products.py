"""产品列表查询 API — 本地数据库"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database import get_db
from app.services.erp_sync import ensure_tables

router = APIRouter(tags=["产品列表"])


@router.get("/", summary="产品列表（分页 + 搜索）")
def api_list_products(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
    keyword: Optional[str] = Query(None, description="货号/品名模糊搜索"),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    ensure_tables(db)

    conditions = []
    params: dict[str, Any] = {}

    if keyword:
        conditions.append("(product_no LIKE :kw OR product_name LIKE :kw OR brand LIKE :kw)")
        params["kw"] = f"%{keyword}%"

    where = " AND ".join(conditions) if conditions else "1=1"

    count_sql = f"SELECT COUNT(*) AS cnt FROM erp_products WHERE {where}"
    total = db.execute(text(count_sql), params).scalar() or 0

    offset = (page - 1) * page_size
    data_sql = f"""
        SELECT id, product_id, product_no, product_name, brand, category,
               color, unit, price, spec, material, image_url, remark, synced_at
        FROM erp_products
        WHERE {where}
        ORDER BY product_no ASC, id ASC
        LIMIT :limit OFFSET :offset
    """
    params["limit"] = page_size
    params["offset"] = offset
    rows = db.execute(text(data_sql), params).mappings().all()

    products = []
    for r in rows:
        products.append({
            "id": r["id"],
            "product_id": r["product_id"] or "",
            "product_no": r["product_no"] or "",
            "product_name": r["product_name"] or "",
            "brand": r["brand"] or "",
            "category": r["category"] or "",
            "color": r["color"] or "",
            "unit": r["unit"] or "",
            "price": float(r["price"] or 0),
            "spec": r["spec"] or "",
            "material": r["material"] or "",
            "image_url": r["image_url"] or "",
            "remark": r["remark"] or "",
            "synced_at": str(r["synced_at"] or ""),
        })

    return {
        "code": 200,
        "data": {
            "list": products,
            "total": total,
            "page": page,
            "page_size": page_size,
        },
    }
