from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.ncloud.client.erp_client import ERPClient
from app.ncloud.dependencies import get_erp_client
from app.ncloud.schemas.sales_orders import (
    AuditActionRequest,
    CreateSalesOrderRequest,
    SalesOrderListResponse,
    SalesOrderDetail,
    UpdateSalesOrderRequest,
    WriteOperationResponse,
)
from app.ncloud.services.sales_orders import audit_order, create_order, get_order_detail, list_orders, update_order

router = APIRouter(tags=["sales_orders"])


@router.get("/sales-orders", response_model=SalesOrderListResponse)
async def api_sales_orders(
    dates: str = Query(..., description="开始日期, 例如 2026-04-01"),
    datee: str = Query(..., description="结束日期, 例如 2026-04-13"),
    state: list[str] | None = Query(default=None, description="单据状态, 默认 0 和 1"),
    page: int = Query(default=1, ge=1),
    rows: int = Query(default=20, ge=1, le=1000),
    erp: ERPClient = Depends(get_erp_client),
) -> SalesOrderListResponse:
    return await list_orders(erp, dates=dates, datee=datee, state=state, page=page, rows=rows)


@router.get("/sales-orders/{dh}", response_model=SalesOrderDetail)
async def api_sales_order_detail(
    dh: str,
    erp: ERPClient = Depends(get_erp_client),
) -> SalesOrderDetail:
    return await get_order_detail(erp, dh)


@router.post("/sales-orders", response_model=WriteOperationResponse, status_code=201)
async def api_create_sales_order(
    req: CreateSalesOrderRequest,
    erp: ERPClient = Depends(get_erp_client),
) -> WriteOperationResponse:
    return await create_order(erp, req)


@router.put("/sales-orders/{dh}", response_model=WriteOperationResponse)
async def api_update_sales_order(
    dh: str,
    req: UpdateSalesOrderRequest,
    erp: ERPClient = Depends(get_erp_client),
) -> WriteOperationResponse:
    return await update_order(erp, dh, req)


@router.post("/sales-orders/{dh}/audit", response_model=WriteOperationResponse)
async def api_audit_sales_order(
    dh: str,
    req: AuditActionRequest,
    erp: ERPClient = Depends(get_erp_client),
) -> WriteOperationResponse:
    return await audit_order(erp, dh, req.action)
