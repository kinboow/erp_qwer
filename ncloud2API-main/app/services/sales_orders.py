from __future__ import annotations

import json

from app.client.erp_client import ERPClient
from app.exceptions import AppException, NotFoundError
from app.schemas.erp_raw.sales_orders import ERPOrderDetail, ERPOrderListRow
from app.schemas.sales_orders import (
    AuditAction,
    CreateOrderDetailRow,
    CreateSalesOrderRequest,
    SalesOrderDetail,
    SalesOrderDetailRow,
    SalesOrderListItem,
    SalesOrderListResponse,
    SalesOrderMainInfo,
    SizeQty,
    UpdateSalesOrderRequest,
    WriteOperationResponse,
)


async def list_orders(
    erp: ERPClient,
    dates: str,
    datee: str,
    state: list[str] | None,
    page: int,
    rows: int,
) -> SalesOrderListResponse:
    payload = await erp.post_form(
        "/SalesManagement/ClothingOrderDd/GridPageListJson",
        {
            "dates": dates,
            "datee": datee,
            "state": json.dumps(state or ["0", "1"]),
            "page": page,
            "rows": rows,
        },
    )

    total = payload.get("total", 0)
    raw_rows = payload.get("rows", [])

    items = []
    for r in raw_rows:
        raw = ERPOrderListRow.model_validate(r)
        items.append(
            SalesOrderListItem(
                state=raw.state,
                print_count=raw.printnum,
                order_no=raw.dh,
                order_date=raw.zhdate,
                creator=raw.zhuser,
                customer_id=raw.khid,
                customer_name=raw.khname,
                customer_tel=raw.khtel,
                customer_addr=raw.khaddr,
                product_no=raw.huohao_mx,
                total_amount=raw.je_sum,
                total_qty=raw.sl_sum,
                salesperson=raw.ywy,
            )
        )

    return SalesOrderListResponse(total=total, rows=items)


async def get_order_detail(erp: ERPClient, dh: str) -> SalesOrderDetail:
    payload = await erp.post_form(
        "/SalesManagement/ClothingOrderDd/GetEntity",
        {"dh": dh},
    )

    raw = ERPOrderDetail.model_validate(payload)

    if not raw.main.dh:
        raise NotFoundError(error_code="ORDER_NOT_FOUND", message=f"订单 {dh} 不存在")

    detail_rows = []
    for row in raw.detail:
        sizes = [SizeQty(size=s.field, qty=s.value or 0) for s in row.chimadetail if s.value]
        detail_rows.append(
            SalesOrderDetailRow(
                brand=row.spbh,
                product_no=row.huohao,
                sizes=sizes,
                grade=row.khgrade,
                customer_product_no=row.khhh,
                product_name=row.spname,
                packaging=row.bzfs,
                color=row.color,
                price=row.price,
                discount=row.zk,
                unit=row.dw,
                remark=row.remark,
            )
        )

    main = SalesOrderMainInfo(
        order_no=raw.main.dh,
        order_date=raw.main.zhdate,
        customer_id=raw.main.khid,
        customer_name=raw.main.khname or None,
        state=raw.main.state,
        creator=raw.main.zhuser,
        customer_tel=raw.main.khtel,
        customer_addr=raw.main.khaddr,
        salesperson=raw.main.ywy,
        shipping_method=raw.main.tyfs,
        shipping_tel=raw.main.shtel,
        shipping_addr=raw.main.shaddr,
        order_ref=raw.main.ddh,
        delivery_date=raw.main.jh_date,
        plan=raw.main.sfplan,
        currency=raw.main.bizhong,
        price_print=raw.main.price_print,
        payment_amount=raw.main.fkje,
        brand=raw.main.main_spbh,
        customer_type=raw.main.khtype,
        contact_person=raw.main.link_man,
        total_qty=raw.main.sl_sum,
        total_amount=raw.main.je_sum,
        discount_amount=raw.main.yhje,
        remark=raw.main.remark,
    )

    return SalesOrderDetail(main=main, detail=detail_rows)


def _build_detail_row(row: CreateOrderDetailRow, sort: int) -> dict:
    total_qty = sum(s.qty for s in row.sizes)
    return {
        "spbh": row.brand,
        "huohao": row.product_no,
        "spname": "",
        "chima": None,
        "zk": row.discount,
        "color": row.color,
        "xs": total_qty,
        "dw": row.unit,
        "price": row.price,
        "remark": row.remark,
        "sort": sort,
        "bzfs": row.packaging,
        "khhh": row.customer_product_no,
        "khgrade": row.grade,
        "huohaoguige": row.product_spec,
        "bcp_huohao": row.semi_product_no,
        "d_ddh": row.linked_order_ref,
        "chimadetail": [
            {"field": s.size, "value": s.qty, "DeleteMark": 0}
            for s in row.sizes
        ],
    }


async def create_order(erp: ERPClient, req: CreateSalesOrderRequest) -> WriteOperationResponse:
    main_data = {
        "dh": "",
        "zhdate": req.order_date,
        "zhuser": "",
        "khid": req.customer_id,
        "khaddr": req.customer_addr,
        "khtel": req.customer_tel,
        "shaddr": req.shipping_addr,
        "shtel": req.shipping_tel,
        "tyfs": req.shipping_method,
        "fkje": req.payment_amount,
        "yhje": 0,
        "remark": req.remark,
        "state": 0,
        "ywy": req.salesperson,
        "ddh": req.order_ref,
        "bizhong": req.currency,
        "sfplan": req.plan,
        "price_print": req.price_print,
        "khtype": req.customer_type,
        "main_spbh": req.brand,
        "jh_date": req.delivery_date,
        "link_man": req.contact_person,
    }

    detail_data = [_build_detail_row(row, i + 1) for i, row in enumerate(req.detail)]

    ht_data = {"dh": "", "guid": "", "zsl": None, "mxsl": None, "xiangshu": None, "DeleteMark": 0}

    payload = await erp.post_form(
        "/SalesManagement/ClothingOrderDd/SubmitForm",
        {
            "isAdd": "true",
            "mainData": json.dumps(main_data, ensure_ascii=False),
            "detailData": json.dumps(detail_data, ensure_ascii=False),
            "fkData": "[]",
            "htData": json.dumps(ht_data, ensure_ascii=False),
        },
    )

    return WriteOperationResponse(dh=payload.get("Data", ""), message=payload.get("Message", ""), state=0)


async def update_order(erp: ERPClient, dh: str, req: UpdateSalesOrderRequest) -> WriteOperationResponse:
    # Fetch current order to merge with updates
    existing = await erp.post_form(
        "/SalesManagement/ClothingOrderDd/GetEntity",
        {"dh": dh},
    )
    raw_main = existing.get("main", {})
    if not raw_main.get("dh"):
        raise NotFoundError(error_code="ORDER_NOT_FOUND", message=f"订单 {dh} 不存在")
    if raw_main.get("state") != 0:
        raise AppException(message=f"订单 {dh} 当前状态不是编辑中，无法修改", status_code=409, error_code="ORDER_NOT_EDITABLE")

    # Merge updates into existing main data
    if req.customer_id is not None:
        raw_main["khid"] = req.customer_id
    if req.order_date is not None:
        raw_main["zhdate"] = req.order_date
    if req.customer_addr is not None:
        raw_main["khaddr"] = req.customer_addr
    if req.customer_tel is not None:
        raw_main["khtel"] = req.customer_tel
    if req.shipping_addr is not None:
        raw_main["shaddr"] = req.shipping_addr
    if req.shipping_tel is not None:
        raw_main["shtel"] = req.shipping_tel
    if req.shipping_method is not None:
        raw_main["tyfs"] = req.shipping_method
    if req.salesperson is not None:
        raw_main["ywy"] = req.salesperson
    if req.order_ref is not None:
        raw_main["ddh"] = req.order_ref
    if req.currency is not None:
        raw_main["bizhong"] = req.currency
    if req.brand is not None:
        raw_main["main_spbh"] = req.brand
    if req.customer_type is not None:
        raw_main["khtype"] = req.customer_type
    if req.remark is not None:
        raw_main["remark"] = req.remark
    if req.delivery_date is not None:
        raw_main["jh_date"] = req.delivery_date
    if req.contact_person is not None:
        raw_main["link_man"] = req.contact_person
    if req.plan is not None:
        raw_main["sfplan"] = req.plan
    if req.price_print is not None:
        raw_main["price_print"] = req.price_print
    if req.payment_amount is not None:
        raw_main["fkje"] = req.payment_amount

    # Build detail data
    if req.detail is not None:
        detail_data = [_build_detail_row(row, i + 1) for i, row in enumerate(req.detail)]
    else:
        detail_data = existing.get("detail", [])

    ht_data = existing.get("ddht", {"dh": dh, "guid": "", "zsl": None, "mxsl": None, "xiangshu": None, "DeleteMark": 0})

    payload = await erp.post_form(
        "/SalesManagement/ClothingOrderDd/SubmitForm",
        {
            "isAdd": "false",
            "mainData": json.dumps(raw_main, ensure_ascii=False),
            "detailData": json.dumps(detail_data, ensure_ascii=False),
            "fkData": json.dumps(existing.get("fkdata", []), ensure_ascii=False),
            "htData": json.dumps(ht_data, ensure_ascii=False),
        },
    )

    return WriteOperationResponse(dh=dh, message=payload.get("Message", ""), state=0)


async def audit_order(erp: ERPClient, dh: str, action: AuditAction) -> WriteOperationResponse:
    if action == AuditAction.audit:
        payload = await erp.post_form(
            "/SalesManagement/ClothingOrderDd/DdshenHe",
            {"dh": dh},
        )
        new_state = 1
    elif action == AuditAction.unaudit:
        payload = await erp.post_form(
            "/SalesManagement/ClothingOrderDd/UnExamine",
            {"dh": dh, "type": "销售订单"},
        )
        new_state = 0
    else:  # void
        payload = await erp.post_form(
            "/SalesManagement/ClothingOrderDd/Delete",
            {"dh": dh},
        )
        new_state = 2

    return WriteOperationResponse(dh=dh, message=payload.get("Message", ""), state=new_state)
