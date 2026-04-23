from __future__ import annotations

import asyncio
import json
import time

from app.ncloud.client.erp_client import ERPClient
from app.ncloud.exceptions import AppException, NotFoundError

# Simple TTL cache: (data, timestamp)
_customer_cache: tuple[list, float] | None = None
_CACHE_TTL = 300  # 5 minutes
_cache_lock = asyncio.Lock()

_REPORT_COLUMN_PARAMS = json.dumps([
    {"field": "zhdate", "title": "日期", "isShow": True},
    {"field": "zdtype", "title": "账单类型", "isShow": True},
    {"field": "xs", "title": "总数量", "isShow": True},
    {"field": "je", "title": "金额", "isShow": True},
    {"field": "yfje", "title": "应收金额", "isShow": True},
    {"field": "fkje", "title": "已收金额", "isShow": True},
    {"field": "qje", "title": "应收余额", "isShow": True},
    {"field": "dh", "title": "单号", "isShow": False},
    {"field": "huohao", "title": "货号", "isShow": False},
    {"field": "color", "title": "颜色", "isShow": False},
    {"field": "price", "title": "销售单价", "isShow": False},
    {"field": "yunhao", "title": "运号", "isShow": False},
    {"field": "remark", "title": "备注", "isShow": False},
], ensure_ascii=False)


async def _get_customers(erp: ERPClient) -> list[dict]:
    """Get customer list with 5-minute TTL cache."""
    global _customer_cache
    async with _cache_lock:
        now = time.monotonic()
        if _customer_cache and (now - _customer_cache[1]) < _CACHE_TTL:
            return _customer_cache[0]
        payload = await erp.post_form_raw("/PublicApp/PublicQuery/GetBaseInfoList", {"param": "customs"})
        # Response is {"customs": [...]}, not a plain list
        customers = payload.get("customs", []) if isinstance(payload, dict) else payload
        _customer_cache = (customers, now)
        return customers


async def resolve_customer_id(erp: ERPClient, customer_name: str) -> str:
    """Resolve customer name to khid. Raises 404 if not found, 422 if ambiguous."""
    customers = await _get_customers(erp)
    matches = [c for c in customers if customer_name in (c.get("name", "") or "")]
    if not matches:
        raise NotFoundError(error_code="CUSTOMER_NOT_FOUND", message=f"未找到客户: {customer_name}")
    if len(matches) > 1:
        raise AppException(
            status_code=422,
            error_code="AMBIGUOUS_CUSTOMER",
            message=f"客户名 '{customer_name}' 匹配到多个结果，请使用 customer_id 直接查询: " +
                    ", ".join(f"{m['bh']}({m.get('name','')})" for m in matches),
        )
    return matches[0]["bh"]


async def get_reconciliation(erp: ERPClient, khid: str, dates: str, datee: str) -> dict:
    """Call GetReportData with multi-page fetching to avoid row caps."""
    filter_rules = json.dumps([
        {"field": "zhdate", "type": "date", "filterOp": "sql", "op": "greaterorequal", "value": dates},
        {"field": "zhdate", "type": "date", "filterOp": "sql", "op": "lessorequal", "value": datee},
        {"field": "isshowqc", "type": "", "filterOp": "other", "op": "equal", "value": "1"},
        {"field": "khid", "filterOp": "sql", "op": "equal", "value": khid},
        {"field": "sfjz", "filterOp": "sql", "op": "notequal", "value": "1"},
    ], ensure_ascii=False)

    rows_per_page = 1000
    all_rows: list = []
    total = 0
    page = 1

    while True:
        resp = await erp.post_form(
            "/SalesManagement/DuizhangOder/GetReportData",
            {
                "sortRules": "zhdate asc,zdtype asc",
                "reportFilterRules": filter_rules,
                "total": "true",
                "subTotalState": "true",
                "reportColumnParams": _REPORT_COLUMN_PARAMS,
                "page": page,
                "rows": rows_per_page,
            },
        )
        page_rows = resp.get("rows", [])
        total = resp.get("total", total)
        all_rows.extend(page_rows)
        if len(page_rows) < rows_per_page:
            break
        page += 1

    return {"total": total, "rows": all_rows}
