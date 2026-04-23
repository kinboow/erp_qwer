from __future__ import annotations

import json

from app.ncloud.client.erp_client import ERPClient
from app.ncloud.schemas.sales_orders import SizeQty
from app.ncloud.schemas.erp_raw.unshipped_report import ERPUnshippedReportRow
from app.ncloud.schemas.unshipped_report import (
    CancelRestoreResponse,
    UnshippedReportItem,
    UnshippedReportResponse,
)


async def query_unshipped_report(
    erp: ERPClient,
    dates: str,
    datee: str,
    customer_id: str | None,
    brand: str | None,
    product_no: str | None,
    page: int,
    rows: int,
) -> UnshippedReportResponse:
    filter_rules: list[dict] = [
        {"field": "sfwg", "type": "", "filterOp": "other", "op": "equal", "value": "0"},
        {"field": "xscdd", "type": "", "filterOp": "other", "op": "equal", "value": "0"},
        {"field": "zhdate", "type": "date", "filterOp": "sql", "op": "greaterorequal", "value": dates},
        {"field": "zhdate", "type": "date", "filterOp": "sql", "op": "lessorequal", "value": datee},
    ]
    if customer_id:
        filter_rules.append({"field": "khid", "filterOp": "sql", "op": "equal", "value": customer_id})
    if brand:
        filter_rules.append({"field": "spbh", "filterOp": "sql", "op": "equal", "value": brand})
    if product_no:
        filter_rules.append({"field": "huohao", "filterOp": "sql", "op": "equal", "value": product_no})

    payload = await erp.post_form(
        "/SalesManagement/ClothingOrderDd/GetWfhReportData",
        {
            "sortRules": "zhdate asc,dh asc,huohao asc",
            "reportFilterRules": json.dumps(filter_rules, ensure_ascii=False),
            "total": "true",
            "subTotalState": "true",
            "subTotalGroupRules": "zhdate,dh",
            "reportColumnParams": "[]",
            "page": page,
            "rows": rows,
        },
    )

    total = payload.get("total", 0)
    raw_rows = payload.get("rows", [])

    items = []
    for r in raw_rows:
        # Skip subtotal rows (empty dh means it's a group subtotal)
        if not r.get("dh"):
            continue
        raw = ERPUnshippedReportRow.model_validate(r)

        unshipped_sizes = [
            SizeQty(size=s.field, qty=s.wfhvalue or 0)
            for s in raw.wfhchimadetail
            if s.wfhvalue
        ]
        order_sizes = [
            SizeQty(size=s.field, qty=s.value or 0)
            for s in raw.chimadetail
            if s.value
        ]

        items.append(
            UnshippedReportItem(
                id=raw.id,
                order_no=raw.dh,
                order_date=raw.zhdate,
                customer_id=raw.khid,
                customer_type=raw.khtype,
                customer_order_no=raw.ddh,
                brand=raw.spbh,
                product_no=raw.huohao,
                product_name=raw.spname,
                color=raw.color,
                unit=raw.dw,
                order_qty=raw.zsl,
                shipped_qty=raw.fhsl,
                returned_qty=raw.thsl,
                unshipped_qty=raw.wfhsl,
                unshipped_amount=raw.wfhje,
                stock_qty=raw.kcsl,
                price=raw.price,
                cost_price=raw.cbprice,
                tag_price=raw.dp_price,
                creator=raw.zhuser,
                remark=raw.remark,
                unshipped_sizes=unshipped_sizes,
                order_sizes=order_sizes,
            )
        )

    return UnshippedReportResponse(total=total, rows=items)


async def cancel_or_restore(
    erp: ERPClient,
    ids: list[str],
    sfwg: int,
) -> CancelRestoreResponse:
    data = [{"id": row_id, "sfwg": sfwg} for row_id in ids]
    payload = await erp.post_form(
        "/SalesManagement/ClothingOrderDd/CancelFh",
        {"data": json.dumps(data, ensure_ascii=False)},
    )
    return CancelRestoreResponse(message=payload.get("Message", "操作成功"))
