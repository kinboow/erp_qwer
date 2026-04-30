"""产品列表查询 API — 本地数据库"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.models import User
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
        conditions.append(
            "(p.product_no LIKE :kw OR p.product_name LIKE :kw OR p.brand LIKE :kw"
            " OR p.product_no IN (SELECT product_no FROM product_name_mappings WHERE alias_name LIKE :kw))"
        )
        params["kw"] = f"%{keyword}%"

    where = " AND ".join(conditions) if conditions else "1=1"

    count_sql = f"SELECT COUNT(*) AS cnt FROM erp_products p WHERE {where}"
    total = db.execute(text(count_sql), params).scalar() or 0

    offset = (page - 1) * page_size
    data_sql = f"""
        SELECT p.id, p.product_id, p.product_no, p.product_name, p.brand, p.category,
               p.color, p.unit, p.price, p.spec, p.material, p.image_url, p.remark, p.is_current_year, p.synced_at,
               (SELECT COUNT(*) FROM product_name_mappings m WHERE m.product_no = p.product_no) AS mapping_count
        FROM erp_products p
        WHERE {where}
        ORDER BY p.product_no ASC, p.id ASC
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
            "is_current_year": bool(r.get("is_current_year")),
            "synced_at": str(r["synced_at"] or ""),
            "mapping_count": r["mapping_count"] or 0,
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


# ---------------------------------------------------------------------------
# 设为本年款 / 取消本年款
# ---------------------------------------------------------------------------

class CurrentYearPayload(BaseModel):
    is_current_year: bool


@router.put("/{product_id}/current-year", summary="设置/取消本年款")
def api_set_current_year(
    product_id: int,
    payload: CurrentYearPayload,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    ensure_tables(db)
    db.execute(
        text("UPDATE erp_products SET is_current_year = :val WHERE id = :id"),
        {"val": 1 if payload.is_current_year else 0, "id": product_id},
    )
    db.commit()
    return {"code": 200, "message": "设置成功"}


@router.post("/batch-current-year", summary="批量设置/取消本年款")
def api_batch_set_current_year(
    payload: dict[str, Any],
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    ensure_tables(db)
    ids = payload.get("ids") or []
    is_current_year = payload.get("is_current_year", True)
    if not ids:
        return {"code": 400, "message": "未选择产品"}
    placeholders = ",".join(str(int(i)) for i in ids)
    db.execute(
        text(f"UPDATE erp_products SET is_current_year = :val WHERE id IN ({placeholders})"),
        {"val": 1 if is_current_year else 0},
    )
    db.commit()
    return {"code": 200, "message": f"已更新 {len(ids)} 个产品"}


@router.get("/current-year", summary="本年产品库（分页 + 搜索）")
def api_list_current_year_products(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
    keyword: Optional[str] = Query(None, description="货号/品名模糊搜索"),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    ensure_tables(db)

    conditions = ["p.is_current_year = 1"]
    params: dict[str, Any] = {}

    if keyword:
        conditions.append(
            "(p.product_no LIKE :kw OR p.product_name LIKE :kw OR p.brand LIKE :kw)"
        )
        params["kw"] = f"%{keyword}%"

    where = " AND ".join(conditions)

    count_sql = f"SELECT COUNT(*) AS cnt FROM erp_products p WHERE {where}"
    total = db.execute(text(count_sql), params).scalar() or 0

    offset = (page - 1) * page_size
    data_sql = f"""
        SELECT p.id, p.product_id, p.product_no, p.product_name, p.brand, p.category,
               p.color, p.unit, p.price, p.spec, p.material, p.image_url, p.remark, p.is_current_year, p.synced_at,
               (SELECT COUNT(*) FROM product_name_mappings m WHERE m.product_no = p.product_no) AS mapping_count
        FROM erp_products p
        WHERE {where}
        ORDER BY p.product_no ASC, p.id ASC
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
            "is_current_year": bool(r.get("is_current_year")),
            "synced_at": str(r["synced_at"] or ""),
            "mapping_count": r["mapping_count"] or 0,
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


# ---------------------------------------------------------------------------
# 名称映射 CRUD
# ---------------------------------------------------------------------------

class AliasPayload(BaseModel):
    alias_name: str


@router.get("/{product_no}/name-mappings", summary="获取货号的名称映射列表")
def api_get_name_mappings(
    product_no: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    ensure_tables(db)
    rows = db.execute(
        text("SELECT id, product_no, alias_name, created_at FROM product_name_mappings WHERE product_no = :pno ORDER BY id ASC"),
        {"pno": product_no},
    ).mappings().all()
    return {
        "code": 200,
        "data": [{"id": r["id"], "product_no": r["product_no"], "alias_name": r["alias_name"], "created_at": str(r["created_at"] or "")} for r in rows],
    }


@router.post("/{product_no}/name-mappings", summary="添加名称映射")
def api_add_name_mapping(
    product_no: str,
    payload: AliasPayload,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    ensure_tables(db)
    alias = payload.alias_name.strip()
    if not alias:
        return {"code": 400, "message": "映射名称不能为空"}

    existing = db.execute(
        text("SELECT id, product_no FROM product_name_mappings WHERE alias_name = :name"),
        {"name": alias},
    ).mappings().first()

    if existing:
        if existing["product_no"] == product_no:
            return {"code": 400, "message": f"该名称已存在于当前货号的映射中"}
        return {"code": 400, "message": f"名称「{alias}」已被货号 {existing['product_no']} 使用，不能重复映射"}

    db.execute(
        text("INSERT INTO product_name_mappings (product_no, alias_name) VALUES (:pno, :name)"),
        {"pno": product_no, "name": alias},
    )
    db.commit()
    return {"code": 200, "message": "添加成功"}


@router.delete("/name-mappings/{mapping_id}", summary="删除名称映射")
def api_delete_name_mapping(
    mapping_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    ensure_tables(db)
    db.execute(text("DELETE FROM product_name_mappings WHERE id = :id"), {"id": mapping_id})
    db.commit()
    return {"code": 200, "message": "删除成功"}


@router.get("/name-mappings/resolve", summary="根据名称解析货号")
def api_resolve_alias(
    name: str = Query(..., description="名称或货号"),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """先精确匹配货号，再查映射表"""
    ensure_tables(db)
    direct = db.execute(
        text("SELECT product_no FROM erp_products WHERE product_no = :name LIMIT 1"),
        {"name": name},
    ).mappings().first()
    if direct:
        return {"code": 200, "data": {"product_no": direct["product_no"], "matched_by": "product_no"}}

    alias = db.execute(
        text("SELECT product_no FROM product_name_mappings WHERE alias_name = :name LIMIT 1"),
        {"name": name},
    ).mappings().first()
    if alias:
        return {"code": 200, "data": {"product_no": alias["product_no"], "matched_by": "alias"}}

    return {"code": 404, "message": f"未找到名称「{name}」对应的货号"}
