from __future__ import annotations

import json
from typing import Any

from app.ncloud.client.erp_client import ERPClient
from app.ncloud.exceptions import ERPUpstreamError
from app.ncloud.schemas.base import CustomerListItem, CustomerListResponse, ProductListItem, ProductListResponse


def _parse_nature(value: Any) -> list[str]:
    if value is None or value == "":
        return []
    if isinstance(value, list):
        return [str(item) for item in value if item is not None]
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return [value]
        if isinstance(parsed, list):
            return [str(item) for item in parsed if item is not None]
        if parsed is None:
            return []
        return [str(parsed)]
    return [str(value)]


def _map_customer(row: dict[str, Any]) -> CustomerListItem:
    return CustomerListItem(
        customer_id=str(row.get("bh") or ""),
        customer_name=row.get("name"),
        short_code=row.get("name_pk"),
        address=row.get("address"),
        phone=row.get("tel1"),
        telephone=row.get("tel2"),
        shipping_address=row.get("shaddr"),
        shipping_phone=row.get("shtel"),
        contact_person=row.get("linkman"),
        state=row.get("state"),
        nature=_parse_nature(row.get("xz")),
        credit_limit=row.get("credit_limits"),
        salesperson=row.get("ywy"),
        customer_type=row.get("khtype"),
        remark=row.get("remark"),
    )


def _map_product(row: dict[str, Any]) -> ProductListItem:
    return ProductListItem(
        product_id=str(row.get("bh") or ""),
        product_no=row.get("bbreed") or row.get("name_pk") or "",
        product_name=row.get("description") or "",
        brand=row.get("lpinpai") or "",
        category=row.get("typename") or "",
        color=row.get("zxsrequire1") or row.get("color") or "",
        unit=row.get("dw") or "",
        price=row.get("xsprice") or 0,
        spec=row.get("zxsrequire2") or "",
        material=row.get("caizhi") or "",
        image_url=row.get("FileUrl") or "",
        remark=row.get("remark") or "",
    )


async def list_products(
    erp: ERPClient,
    page: int,
    rows: int,
) -> ProductListResponse:
    payload = await erp.post_form(
        "/BaseInfo/SysHuohao/GridPageListJson",
        {"page": page, "rows": rows},
    )
    if "total" not in payload or "rows" not in payload or not isinstance(payload["rows"], list):
        raise ERPUpstreamError("ERP product list returned an unexpected shape")

    return ProductListResponse(
        total=payload["total"],
        rows=[_map_product(row) for row in payload["rows"]],
    )


async def list_customers(
    erp: ERPClient,
    page: int,
    rows: int,
    search: str | None = None,
) -> CustomerListResponse:
    data: dict[str, Any] = {"page": page, "rows": rows}
    if search:
        data["search"] = search

    payload = await erp.post_form(
        "/BaseInfo/SysCustoms/GridPageListJson",
        data,
    )
    if "total" not in payload or "rows" not in payload or not isinstance(payload["rows"], list):
        raise ERPUpstreamError("ERP customer list returned an unexpected shape")

    return CustomerListResponse(
        total=payload["total"],
        rows=[_map_customer(row) for row in payload["rows"]],
    )
