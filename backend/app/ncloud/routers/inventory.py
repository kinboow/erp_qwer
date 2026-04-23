from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.ncloud.client.erp_client import ERPClient
from app.ncloud.dependencies import get_erp_client
from app.ncloud.schemas.inventory import InventoryResponse
from app.ncloud.services.inventory import query_inventory

router = APIRouter(prefix="/inventory", tags=["inventory"])


@router.get("", response_model=InventoryResponse)
async def api_inventory(
    warehouse: str | None = Query(default=None),
    product_type: str | None = Query(default=None),
    product_no: str | None = Query(default=None),
    product_name: str | None = Query(default=None),
    show_zero: bool = Query(default=False),
    show_negative: bool = Query(default=False),
    page: int = Query(default=1, ge=1),
    rows: int = Query(default=200, ge=1, le=5000),
    erp: ERPClient = Depends(get_erp_client),
) -> InventoryResponse:
    return await query_inventory(
        erp, warehouse=warehouse, product_type=product_type,
        product_no=product_no, product_name=product_name,
        show_zero=show_zero, show_negative=show_negative,
        page=page, rows=rows,
    )
