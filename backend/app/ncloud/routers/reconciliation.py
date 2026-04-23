from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.ncloud.client.erp_client import ERPClient
from app.ncloud.dependencies import get_erp_client
from app.ncloud.exceptions import AppException
from app.ncloud.schemas.reconciliation import ReconciliationResponse, ReconciliationRow, ReconciliationSummary
from app.ncloud.services.reconciliation import get_reconciliation, resolve_customer_id

router = APIRouter(prefix="/sales-reconciliation", tags=["reconciliation"])


@router.get("", response_model=ReconciliationResponse)
async def api_reconciliation(
    dates: str = Query(..., description="起始日期, 例如 2026-04-01"),
    datee: str = Query(..., description="结束日期, 例如 2026-04-14"),
    customer_name: str | None = Query(default=None),
    customer_id: str | None = Query(default=None),
    erp: ERPClient = Depends(get_erp_client),
) -> ReconciliationResponse:
    if not customer_name and not customer_id:
        raise AppException(
            status_code=422,
            error_code="MISSING_CUSTOMER",
            message="必须提供 customer_name 或 customer_id",
        )

    khid = customer_id or await resolve_customer_id(erp, customer_name)

    # Always fetch all rows (no pagination) so summary is computed from complete data
    payload = await get_reconciliation(erp, khid=khid, dates=dates, datee=datee)

    total = payload.get("total", 0) if isinstance(payload, dict) else 0
    raw_rows = payload.get("rows", []) if isinstance(payload, dict) else []

    row_objects = [
        ReconciliationRow(
            date=r.get("zhdate"),
            type=r.get("zdtype"),
            qty=r.get("xs"),
            amount=r.get("je"),
            receivable=r.get("yfje"),
            received=r.get("fkje"),
            balance=r.get("qje"),
            order_no=r.get("dh"),
        )
        for r in raw_rows
    ]

    # Compute summary from all rows (always complete — no pagination)
    opening_row = next((r for r in row_objects if "期初" in (r.type or "")), None)
    opening_balance = opening_row.balance if opening_row and opening_row.balance is not None else 0.0
    total_shipment = sum(r.amount or 0 for r in row_objects if "发货" in (r.type or ""))
    total_return = sum(r.amount or 0 for r in row_objects if "退货" in (r.type or ""))
    total_payment = sum(r.received or 0 for r in row_objects)
    closing_balance = row_objects[-1].balance if row_objects else 0.0

    summary = ReconciliationSummary(
        customer_name=customer_name,
        date_from=dates,
        date_to=datee,
        opening_balance=opening_balance,
        total_shipment=total_shipment,
        total_return=total_return,
        total_payment=total_payment,
        closing_balance=closing_balance,
    )

    return ReconciliationResponse(summary=summary, total=total, rows=row_objects)
