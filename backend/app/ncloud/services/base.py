from __future__ import annotations

import json
from typing import Any

from app.ncloud.client.erp_client import ERPClient
from app.ncloud.exceptions import ERPUpstreamError
from app.ncloud.schemas.base import CustomerListItem, CustomerListResponse


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
