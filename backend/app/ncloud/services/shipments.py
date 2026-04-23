from __future__ import annotations

import json

from app.ncloud.client.erp_client import ERPClient
from app.ncloud.exceptions import AppException, NotFoundError
from app.ncloud.schemas.sales_orders import AuditAction, SizeQty, WriteOperationResponse
from app.ncloud.schemas.erp_raw.shipments import ERPShipmentDetail, ERPShipmentListRow
from app.ncloud.schemas.shipments import (
    CreateShipmentDetailRow,
    CreateShipmentRequest,
    ShipmentDetail,
    ShipmentDetailRow,
    ShipmentListItem,
    ShipmentListResponse,
    ShipmentMainInfo,
    UpdateShipmentRequest,
)


async def list_shipments(
    erp: ERPClient,
    dates: str,
    datee: str,
    state: list[str] | None,
    page: int,
    rows: int,
) -> ShipmentListResponse:
    payload = await erp.post_form(
        "/SalesManagement/ClothingOrder/GridPageListJson",
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
        raw = ERPShipmentListRow.model_validate(r)
        items.append(
            ShipmentListItem(
                order_no=raw.dh,
                order_date=raw.zhdate,
                customer_id=raw.khid,
                customer_addr=raw.khaddr,
                state=raw.state,
                total_qty=raw.fhzsl,
                total_amount=raw.je_sum,
                tracking_no=raw.yunhao,
                customer_name=raw.khname,
                print_count=raw.printnum,
                salesperson=raw.ywy,
                shipping_addr=raw.shaddr,
                shipping_method=raw.tyfs,
                freight=raw.yunfei,
            )
        )

    return ShipmentListResponse(total=total, rows=items)


async def get_shipment_detail(erp: ERPClient, dh: str) -> ShipmentDetail:
    payload = await erp.post_form(
        "/SalesManagement/ClothingOrder/GetEntity",
        {"dh": dh},
    )

    raw = ERPShipmentDetail.model_validate(payload)

    if not raw.main.dh:
        raise NotFoundError(error_code="SHIPMENT_NOT_FOUND", message=f"发货单 {dh} 不存在")

    detail_rows = []
    for row in raw.detail:
        sizes = [SizeQty(size=s.field, qty=s.value or 0) for s in row.chimadetail if s.value]
        detail_rows.append(
            ShipmentDetailRow(
                product_no=row.huohao,
                color=row.color,
                sizes=sizes,
                order_ref=row.ddid,
                brand=row.spbh,
                customer_product_no=row.khhh,
                product_name=row.spname,
                packaging=row.bzfs,
                price=row.price,
                discount=row.zk,
                unit=row.dw,
                remark=row.remark,
            )
        )

    main = ShipmentMainInfo(
        order_no=raw.main.dh,
        order_date=raw.main.zhdate,
        customer_id=raw.main.khid,
        customer_name=raw.main.khname,
        creator=raw.main.zhuser,
        handler=raw.main.jsr,
        customer_tel=raw.main.khtel,
        customer_addr=raw.main.khaddr,
        state=raw.main.state,
        warehouse=raw.main.ck,
        shipping_method=raw.main.tyfs,
        shipping_tel=raw.main.shtel,
        shipping_addr=raw.main.shaddr,
        tracking_no=raw.main.yunhao,
        freight=raw.main.yunfei,
        payment_amount=raw.main.fkje,
        salesperson=raw.main.ywy,
        delivery_person=raw.main.shuser,
        customer_type=raw.main.khtype,
        currency=raw.main.bizhong,
        price_print=raw.main.price_print,
        contact_person=raw.main.link_man,
        contact_tel=raw.main.tel1,
        total_qty=raw.main.fhzsl,
        total_amount=raw.main.je_sum,
        remark=raw.main.remark,
    )

    return ShipmentDetail(main=main, detail=detail_rows)


def _build_shipment_detail_row(row: CreateShipmentDetailRow, sort: int) -> dict:
    total_qty = sum(s.qty for s in row.sizes)
    return {
        "spbh": row.brand,
        "huohao": row.product_no,
        "spname": "",
        "zk": row.discount,
        "color": row.color,
        "xs": total_qty,
        "dw": row.unit,
        "price": row.price,
        "remark": row.remark,
        "sort": sort,
        "bzfs": row.packaging,
        "khhh": row.customer_product_no,
        "ddid": row.order_ref_id,
        "huohaoguige": row.product_spec,
        "bcp_huohao": row.semi_product_no,
        "caizhi": row.material,
        "chimadetail": [
            {"field": s.size, "value": s.qty, "DeleteMark": 0}
            for s in row.sizes
        ],
    }


async def create_shipment(erp: ERPClient, req: CreateShipmentRequest) -> WriteOperationResponse:
    main_data = {
        "dh": "",
        "zhdate": req.shipment_date,
        "zhuser": "",
        "khid": req.customer_id,
        "khaddr": req.customer_addr,
        "shaddr": req.shipping_addr,
        "shtel": req.shipping_tel,
        "shuser": req.delivery_person,
        "tyfs": req.shipping_method,
        "yunhao": req.tracking_no,
        "yunfei": req.freight,
        "fkje": req.payment_amount,
        "yhje": 0,
        "remark": req.remark,
        "state": 0,
        "ywy": req.salesperson,
        "ck": req.warehouse,
        "bizhong": req.currency,
        "price_print": req.price_print,
        "tel1": req.contact_tel,
        "link_man": req.contact_person,
        "khtype": req.customer_type,
        "jsr": req.handler,
        "ddh": "",
    }

    detail_data = [_build_shipment_detail_row(row, i + 1) for i, row in enumerate(req.detail)]

    payload = await erp.post_form(
        "/SalesManagement/ClothingOrder/SubmitForm",
        {
            "isAdd": "true",
            "mainData": json.dumps(main_data, ensure_ascii=False),
            "detailData": json.dumps(detail_data, ensure_ascii=False),
            "fkData": "[]",
            "resend": "0",
            "khqk": "",
        },
    )

    return WriteOperationResponse(dh=payload.get("Data", ""), message=payload.get("Message", ""), state=0)


async def update_shipment(erp: ERPClient, dh: str, req: UpdateShipmentRequest) -> WriteOperationResponse:
    existing = await erp.post_form(
        "/SalesManagement/ClothingOrder/GetEntity",
        {"dh": dh},
    )
    raw_main = existing.get("main", {})
    if not raw_main.get("dh"):
        raise NotFoundError(error_code="SHIPMENT_NOT_FOUND", message=f"发货单 {dh} 不存在")
    if raw_main.get("state") != 0:
        raise AppException(message=f"发货单 {dh} 当前状态不是编辑中，无法修改", status_code=409, error_code="SHIPMENT_NOT_EDITABLE")

    if req.customer_id is not None:
        raw_main["khid"] = req.customer_id
    if req.shipment_date is not None:
        raw_main["zhdate"] = req.shipment_date
    if req.warehouse is not None:
        raw_main["ck"] = req.warehouse
    if req.customer_addr is not None:
        raw_main["khaddr"] = req.customer_addr
    if req.shipping_addr is not None:
        raw_main["shaddr"] = req.shipping_addr
    if req.shipping_tel is not None:
        raw_main["shtel"] = req.shipping_tel
    if req.shipping_method is not None:
        raw_main["tyfs"] = req.shipping_method
    if req.delivery_person is not None:
        raw_main["shuser"] = req.delivery_person
    if req.tracking_no is not None:
        raw_main["yunhao"] = req.tracking_no
    if req.freight is not None:
        raw_main["yunfei"] = req.freight
    if req.salesperson is not None:
        raw_main["ywy"] = req.salesperson
    if req.contact_person is not None:
        raw_main["link_man"] = req.contact_person
    if req.contact_tel is not None:
        raw_main["tel1"] = req.contact_tel
    if req.currency is not None:
        raw_main["bizhong"] = req.currency
    if req.customer_type is not None:
        raw_main["khtype"] = req.customer_type
    if req.remark is not None:
        raw_main["remark"] = req.remark
    if req.handler is not None:
        raw_main["jsr"] = req.handler
    if req.price_print is not None:
        raw_main["price_print"] = req.price_print
    if req.payment_amount is not None:
        raw_main["fkje"] = req.payment_amount

    if req.detail is not None:
        detail_data = [_build_shipment_detail_row(row, i + 1) for i, row in enumerate(req.detail)]
    else:
        detail_data = existing.get("detail", [])

    payload = await erp.post_form(
        "/SalesManagement/ClothingOrder/SubmitForm",
        {
            "isAdd": "false",
            "mainData": json.dumps(raw_main, ensure_ascii=False),
            "detailData": json.dumps(detail_data, ensure_ascii=False),
            "fkData": json.dumps(existing.get("fkdata", []), ensure_ascii=False),
            "resend": "0",
            "khqk": "",
        },
    )

    return WriteOperationResponse(dh=dh, message=payload.get("Message", ""), state=0)


async def audit_shipment(erp: ERPClient, dh: str, action: AuditAction) -> WriteOperationResponse:
    if action == AuditAction.audit:
        payload = await erp.post_form(
            "/SalesManagement/ClothingOrder/shenHe",
            {"dh": dh},
        )
        new_state = 1
    elif action == AuditAction.unaudit:
        payload = await erp.post_form(
            "/SalesManagement/ClothingOrder/UnExamine",
            {"dh": dh},
        )
        new_state = 0
    else:  # void
        payload = await erp.post_form(
            "/SalesManagement/ClothingOrder/Delete",
            {"dh": dh},
        )
        new_state = 2

    return WriteOperationResponse(dh=dh, message=payload.get("Message", ""), state=new_state)
