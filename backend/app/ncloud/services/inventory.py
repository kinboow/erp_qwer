from __future__ import annotations

import json

from app.ncloud.client.erp_client import ERPClient
from app.ncloud.schemas.sales_orders import SizeQty
from app.ncloud.schemas.erp_raw.inventory import ERPInventoryRow
from app.ncloud.schemas.inventory import InventoryItem, InventoryResponse


async def query_inventory(
    erp: ERPClient,
    warehouse: str | None,
    product_type: str | None,
    product_no: str | None,
    product_name: str | None,
    show_zero: bool,
    show_negative: bool,
    page: int,
    rows: int,
) -> InventoryResponse:
    filter_rules: list[dict] = []

    if not show_zero:
        filter_rules.append(
            {"field": "zeroInventory", "type": "", "filterOp": "other", "op": "equal", "value": "0"}
        )
    if not show_negative:
        filter_rules.append(
            {"field": "fuInventory", "type": "", "filterOp": "other", "op": "equal", "value": "0"}
        )
    if warehouse:
        filter_rules.append({"field": "ck", "filterOp": "sql", "op": "equal", "value": warehouse})
    if product_type:
        filter_rules.append({"field": "huohaotypename", "filterOp": "sql", "op": "equal", "value": product_type})
    if product_no:
        filter_rules.append({"field": "huohao", "filterOp": "sql", "op": "equal", "value": product_no})
    if product_name:
        filter_rules.append({"field": "description", "filterOp": "sql", "op": "like", "value": product_name})

    payload = await erp.post_form(
        "/CpHandwork/HandWorkCpInventory/GetZReportDataCosswise",
        {
            "sortRules": "ck asc,huohao asc,color asc",
            "reportFilterRules": json.dumps(filter_rules, ensure_ascii=False),
            "total": "true",
            "subTotalState": "true",
            "subTotalGroupRules": "",
            "reportColumnParams": "[]",
            "page": page,
            "rows": rows,
        },
    )

    total = payload.get("total", 0)
    raw_rows = payload.get("rows", [])

    items = []
    for r in raw_rows:
        raw = ERPInventoryRow.model_validate(r)

        sizes = [
            SizeQty(size=s.field, qty=s.value or 0)
            for s in raw.chimadetail
            if s.value
        ]

        items.append(
            InventoryItem(
                warehouse=raw.ck,
                product_type=raw.huohaotypename,
                product_no=raw.huohao,
                product_name=raw.description,
                material=raw.caizhi,
                image_url=raw.FileUrl,
                color=raw.color,
                unit=raw.dw,
                qty=raw.sl,
                sale_price=raw.xsprice,
                cost_price=raw.cbprice,
                amount=raw.je,
                in_transit_qty=raw.ztsl,
                sizes=sizes,
            )
        )

    return InventoryResponse(total=total, rows=items)
