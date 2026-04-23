from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.client.erp_client import ERPClient
from app.dependencies import get_erp_client
from app.schemas.sales_orders import AuditActionRequest, WriteOperationResponse
from app.schemas.shipments import (
    CreateShipmentRequest,
    ShipmentDetail,
    ShipmentListResponse,
    UpdateShipmentRequest,
)
from app.services.shipments import (
    audit_shipment,
    create_shipment,
    get_shipment_detail,
    list_shipments,
    update_shipment,
)

router = APIRouter(prefix="/api/sales-shipments", tags=["shipments"])


@router.get("", response_model=ShipmentListResponse)
async def api_shipments_list(
    dates: str = Query(...),
    datee: str = Query(...),
    state: list[str] | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    rows: int = Query(default=20, ge=1, le=1000),
    erp: ERPClient = Depends(get_erp_client),
) -> ShipmentListResponse:
    return await list_shipments(erp, dates=dates, datee=datee, state=state, page=page, rows=rows)


@router.get("/{dh}", response_model=ShipmentDetail)
async def api_shipment_detail(
    dh: str,
    erp: ERPClient = Depends(get_erp_client),
) -> ShipmentDetail:
    return await get_shipment_detail(erp, dh)


@router.post("", response_model=WriteOperationResponse, status_code=201)
async def api_create_shipment(
    req: CreateShipmentRequest,
    erp: ERPClient = Depends(get_erp_client),
) -> WriteOperationResponse:
    return await create_shipment(erp, req)


@router.put("/{dh}", response_model=WriteOperationResponse)
async def api_update_shipment(
    dh: str,
    req: UpdateShipmentRequest,
    erp: ERPClient = Depends(get_erp_client),
) -> WriteOperationResponse:
    return await update_shipment(erp, dh, req)


@router.post("/{dh}/audit", response_model=WriteOperationResponse)
async def api_audit_shipment(
    dh: str,
    req: AuditActionRequest,
    erp: ERPClient = Depends(get_erp_client),
) -> WriteOperationResponse:
    return await audit_shipment(erp, dh, req.action)
