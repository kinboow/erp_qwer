from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.ncloud.client.erp_client import ERPClient
from app.ncloud.dependencies import get_erp_client
from app.ncloud.schemas.unshipped_report import (
    CancelRestoreRequest,
    CancelRestoreResponse,
    UnshippedReportResponse,
)
from app.ncloud.services.unshipped_report import cancel_or_restore, query_unshipped_report

router = APIRouter(prefix="/unshipped-report", tags=["unshipped-report"])


@router.get("", response_model=UnshippedReportResponse)
async def api_unshipped_report(
    dates: str = Query(...),
    datee: str = Query(...),
    customer_id: str | None = Query(default=None),
    brand: str | None = Query(default=None),
    product_no: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    rows: int = Query(default=200, ge=1, le=5000),
    erp: ERPClient = Depends(get_erp_client),
) -> UnshippedReportResponse:
    return await query_unshipped_report(
        erp, dates=dates, datee=datee,
        customer_id=customer_id, brand=brand, product_no=product_no,
        page=page, rows=rows,
    )


@router.post("/cancel", response_model=CancelRestoreResponse)
async def api_cancel_shipment(
    req: CancelRestoreRequest,
    erp: ERPClient = Depends(get_erp_client),
) -> CancelRestoreResponse:
    return await cancel_or_restore(erp, req.ids, sfwg=1)


@router.post("/restore", response_model=CancelRestoreResponse)
async def api_restore_order(
    req: CancelRestoreRequest,
    erp: ERPClient = Depends(get_erp_client),
) -> CancelRestoreResponse:
    return await cancel_or_restore(erp, req.ids, sfwg=0)
