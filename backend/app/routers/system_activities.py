"""系统动态 API 路由 —— 混合时间线（订单 + 发货单 + 系统事件）"""

from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.models import User

router = APIRouter(tags=["系统动态"])


def _ok(data=None, message="success"):
    resp = {"code": 200, "message": message}
    if data is not None:
        resp["data"] = data
    return resp


def _safe_rows(db: Session, sql: str) -> list:
    try:
        return [dict(r) for r in db.execute(text(sql)).mappings().all()]
    except Exception:
        return []


def _build_timeline(db: Session, keyword: Optional[str] = None) -> list[dict]:
    """构建混合时间线列表（全量），与首页系统动态逻辑一致"""
    items = []

    # 销售订单
    orders = _safe_rows(db, """
        SELECT order_no, order_date, state, customer_name, total_amount
        FROM erp_sales_orders ORDER BY order_date DESC LIMIT 200
    """)
    for r in orders:
        state_text = "已审核" if r.get("state") == 1 else "待审核"
        amt = float(r.get("total_amount") or 0)
        content = f"销售订单 {r['order_no']}（{r.get('customer_name', '')}）{state_text}，金额 ¥{amt:,.2f}"
        items.append({
            "content": content,
            "time": r.get("order_date", ""),
            "type": "important" if r.get("state") != 1 else "normal",
        })

    # 销售发货单
    ships = _safe_rows(db, """
        SELECT order_no, order_date, state, customer_name
        FROM erp_sales_shipments ORDER BY order_date DESC LIMIT 200
    """)
    for r in ships:
        state_text = "已审核" if r.get("state") == 1 else "待审核"
        content = f"发货单 {r['order_no']}（{r.get('customer_name', '')}）{state_text}"
        items.append({
            "content": content,
            "time": r.get("order_date", ""),
            "type": "important" if r.get("state") != 1 else "normal",
        })

    # 系统事件（同步失败等）
    try:
        from app.services.system_activities import ensure_table
        ensure_table(db)
        sys_rows = [dict(r) for r in db.execute(
            text("SELECT * FROM system_activities ORDER BY created_at DESC LIMIT 200")
        ).mappings().all()]
        for a in sys_rows:
            created = a.get("created_at")
            time_str = created.strftime("%Y-%m-%d %H:%M:%S") if hasattr(created, "strftime") else str(created or "")
            raw_type = a.get("type", "")
            mapped = "urgent" if raw_type in ("error", "urgent") else "important" if raw_type in ("warning", "important") else "normal"
            items.append({
                "content": a.get("content") or a.get("title", ""),
                "time": time_str,
                "type": mapped,
            })
    except Exception:
        pass

    # 按关键词过滤
    if keyword:
        kw = keyword.lower()
        items = [i for i in items if kw in (i.get("content") or "").lower()]

    # 按时间倒序
    items.sort(key=lambda x: x["time"], reverse=True)
    return items


@router.get("", summary="获取系统动态时间线（分页）")
async def api_list(
    keyword: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    all_items = _build_timeline(db, keyword=keyword)
    total = len(all_items)
    start = (page - 1) * page_size
    items = all_items[start:start + page_size]
    return _ok(data={
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": items,
    })
