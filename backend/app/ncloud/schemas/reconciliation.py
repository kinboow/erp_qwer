from __future__ import annotations

from pydantic import BaseModel


class ReconciliationRow(BaseModel):
    date: str | None = None        # ERP: zhdate
    type: str | None = None        # ERP: zdtype
    qty: float | None = None       # ERP: xs
    amount: float | None = None    # ERP: je
    receivable: float | None = None   # ERP: yfje
    received: float | None = None     # ERP: fkje
    balance: float | None = None      # ERP: qje
    order_no: str | None = None       # ERP: dh


class ReconciliationSummary(BaseModel):
    customer_name: str | None = None
    date_from: str = ""
    date_to: str = ""
    opening_balance: float = 0.0
    total_shipment: float = 0.0
    total_return: float = 0.0
    total_payment: float = 0.0
    closing_balance: float = 0.0


class ReconciliationResponse(BaseModel):
    summary: ReconciliationSummary
    total: int = 0
    rows: list[ReconciliationRow] = []
