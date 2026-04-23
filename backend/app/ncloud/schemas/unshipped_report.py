from __future__ import annotations

from pydantic import BaseModel, Field

from app.ncloud.schemas.sales_orders import SizeQty


class UnshippedReportItem(BaseModel):
    id: str                               # 行唯一标识
    order_no: str                         # ERP: dh
    order_date: str                       # ERP: zhdate
    customer_id: str                      # ERP: khid
    customer_type: str | None = ""        # ERP: khtype
    customer_order_no: str | None = ""    # ERP: ddh
    brand: str | None = ""               # ERP: spbh
    product_no: str                       # ERP: huohao
    product_name: str | None = ""         # ERP: spname
    color: str | None = ""               # ERP: color
    unit: str | None = ""                 # ERP: dw
    order_qty: float | None = 0           # ERP: zsl
    shipped_qty: float | None = 0         # ERP: fhsl
    returned_qty: float | None = 0        # ERP: thsl
    unshipped_qty: float | None = 0       # ERP: wfhsl
    unshipped_amount: float | None = 0    # ERP: wfhje
    stock_qty: float | None = 0           # ERP: kcsl
    price: float | None = 0              # ERP: price
    cost_price: float | None = 0          # ERP: cbprice
    tag_price: float | None = 0           # ERP: dp_price
    creator: str | None = ""              # ERP: zhuser
    remark: str | None = ""               # ERP: remark
    unshipped_sizes: list[SizeQty] = []   # 未发货各尺码
    order_sizes: list[SizeQty] = []       # 订单各尺码


class UnshippedReportResponse(BaseModel):
    total: int
    rows: list[UnshippedReportItem]


class CancelRestoreRequest(BaseModel):
    ids: list[str] = Field(..., min_length=1, description="报表行 ID 列表")


class CancelRestoreResponse(BaseModel):
    message: str
