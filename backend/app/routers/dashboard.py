"""数据看板 API"""
from datetime import datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User

router = APIRouter(tags=["数据看板"])


def _safe_scalar(db: Session, sql: str):
    """安全执行 SQL 并返回标量值，表不存在等异常时返回 0"""
    try:
        return db.execute(text(sql)).scalar() or 0
    except Exception:
        return 0


def _safe_rows(db: Session, sql: str) -> list:
    """安全执行 SQL 并返回行列表，异常时返回空列表"""
    try:
        return [dict(r) for r in db.execute(text(sql)).mappings().all()]
    except Exception:
        return []


@router.get("/stats", summary="看板统计数据")
def dashboard_stats(
    time_range: str = Query("7d", alias="range"),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    today = datetime.now().strftime("%Y-%m-%d")
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

    # 解析趋势图天数
    range_days = {"1d": 1, "7d": 7, "30d": 30}.get(time_range, 7)

    # 用户总数（status=1 为启用）
    try:
        user_count = db.query(User).filter(User.status == 1).count()
    except Exception:
        user_count = 0

    # 产品总数
    product_count = _safe_scalar(db, "SELECT COUNT(*) FROM erp_products")

    # 订单统计
    total_orders = _safe_scalar(db, "SELECT COUNT(*) FROM erp_sales_orders")
    pending_orders = _safe_scalar(
        db, "SELECT COUNT(*) FROM erp_sales_orders WHERE state = 0"
    )
    today_orders = _safe_scalar(
        db, f"SELECT COUNT(*) FROM erp_sales_orders WHERE order_date LIKE '{today}%'"
    )
    yesterday_orders = _safe_scalar(
        db, f"SELECT COUNT(*) FROM erp_sales_orders WHERE order_date LIKE '{yesterday}%'"
    )

    # 发货单统计
    total_shipments = _safe_scalar(db, "SELECT COUNT(*) FROM erp_sales_shipments")
    today_shipments = _safe_scalar(
        db, f"SELECT COUNT(*) FROM erp_sales_shipments WHERE order_date LIKE '{today}%'"
    )
    yesterday_shipments = _safe_scalar(
        db, f"SELECT COUNT(*) FROM erp_sales_shipments WHERE order_date LIKE '{yesterday}%'"
    )

    # 本月营收（已审核订单金额）
    month_start = datetime.now().strftime("%Y-%m-01")
    last_month_start = (datetime.now().replace(day=1) - timedelta(days=1)).strftime("%Y-%m-01")
    last_month_end = datetime.now().replace(day=1).strftime("%Y-%m-01")

    month_revenue = float(_safe_scalar(
        db,
        f"SELECT COALESCE(SUM(total_amount),0) FROM erp_sales_orders "
        f"WHERE state = 1 AND order_date >= '{month_start}'"
    ))
    last_month_revenue = float(_safe_scalar(
        db,
        f"SELECT COALESCE(SUM(total_amount),0) FROM erp_sales_orders "
        f"WHERE state = 1 AND order_date >= '{last_month_start}' AND order_date < '{last_month_end}'"
    ))

    # 趋势图数据
    trend_orders = []
    trend_shipments = []

    if time_range == "1d":
        # 近24小时，每小时一个点
        now = datetime.now()
        for i in range(23, -1, -1):
            h_start = (now - timedelta(hours=i)).strftime("%Y-%m-%d %H")
            cnt_o = _safe_scalar(
                db, f"SELECT COUNT(*) FROM erp_sales_orders WHERE order_date LIKE '{h_start}%'"
            )
            cnt_s = _safe_scalar(
                db, f"SELECT COUNT(*) FROM erp_sales_shipments WHERE order_date LIKE '{h_start}%'"
            )
            trend_orders.append({"date": f"{h_start}:00", "count": cnt_o})
            trend_shipments.append({"date": f"{h_start}:00", "count": cnt_s})
    else:
        for i in range(range_days - 1, -1, -1):
            d = (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")
            cnt_o = _safe_scalar(
                db, f"SELECT COUNT(*) FROM erp_sales_orders WHERE order_date LIKE '{d}%'"
            )
            cnt_s = _safe_scalar(
                db, f"SELECT COUNT(*) FROM erp_sales_shipments WHERE order_date LIKE '{d}%'"
            )
            trend_orders.append({"date": d, "count": cnt_o})
            trend_shipments.append({"date": d, "count": cnt_s})

    # 待审核下游订单
    pending_downstream = _safe_scalar(
        db, "SELECT COUNT(*) FROM downstream_orders WHERE status = 'pending'"
    )

    # 服务状态
    wechat_online = False
    try:
        from app.services.wechat_health import get_wechat_health_status
        wechat_status = get_wechat_health_status()
        wechat_online = wechat_status.get("online", False)
    except Exception:
        pass

    erp_online = False
    try:
        from app.services.erp_health import get_erp_health_status
        erp_status = get_erp_health_status()
        erp_online = erp_status.get("online", False)
    except Exception:
        pass

    # 最近动态：最新10条订单和发货单混合
    recent_activities = []

    recent_orders = _safe_rows(db, """
        SELECT order_no, order_date, state, customer_name, total_amount
        FROM erp_sales_orders
        ORDER BY order_date DESC, order_no DESC
        LIMIT 5
    """)
    for r in recent_orders:
        state_text = "已审核" if r.get("state") == 1 else "待审核"
        amt = float(r.get("total_amount") or 0)
        recent_activities.append({
            "content": f"销售订单 {r['order_no']}（{r.get('customer_name', '')}）{state_text}，金额 ¥{amt:,.2f}",
            "time": r.get("order_date", ""),
            "type": "important" if r.get("state") != 1 else "normal",
        })

    recent_ships = _safe_rows(db, """
        SELECT order_no, order_date, state, customer_name, total_amount
        FROM erp_sales_shipments
        ORDER BY order_date DESC, order_no DESC
        LIMIT 5
    """)
    for r in recent_ships:
        state_text = "已审核" if r.get("state") == 1 else "待审核"
        recent_activities.append({
            "content": f"发货单 {r['order_no']}（{r.get('customer_name', '')}）{state_text}",
            "time": r.get("order_date", ""),
            "type": "important" if r.get("state") != 1 else "normal",
        })

    # 系统动态（同步失败等）
    try:
        from app.services.system_activities import get_recent_activities
        sys_acts = get_recent_activities(db, limit=5)
        for a in sys_acts:
            created = a.get("created_at")
            time_str = created.strftime("%Y-%m-%d %H:%M:%S") if hasattr(created, "strftime") else str(created or "")
            raw_type = a.get("type", "")
            mapped = "urgent" if raw_type in ("error", "urgent") else "important" if raw_type in ("warning", "important") else "normal"
            recent_activities.append({
                "content": a.get("content") or a.get("title", ""),
                "time": time_str,
                "type": mapped,
            })
    except Exception:
        pass

    # 按时间倒序排列，取最新10条
    recent_activities.sort(key=lambda x: x["time"], reverse=True)
    recent_activities = recent_activities[:10]

    return {
        "code": 200,
        "data": {
            "user_count": user_count,
            "product_count": product_count,
            "total_orders": total_orders,
            "pending_orders": pending_orders,
            "today_orders": today_orders,
            "yesterday_orders": yesterday_orders,
            "total_shipments": total_shipments,
            "today_shipments": today_shipments,
            "yesterday_shipments": yesterday_shipments,
            "month_revenue": month_revenue,
            "last_month_revenue": last_month_revenue,
            "pending_downstream": pending_downstream,
            "daily_orders": trend_orders,
            "daily_shipments": trend_shipments,
            "recent_activities": recent_activities,
            "wechat_online": wechat_online,
            "erp_online": erp_online,
        }
    }
