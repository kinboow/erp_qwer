from __future__ import annotations

from pydantic import BaseModel

from app.schemas.sales_orders import SizeQty


class InventoryItem(BaseModel):
    warehouse: str                    # ERP: ck
    product_type: str | None = ""     # ERP: huohaotypename
    product_no: str                   # ERP: huohao
    product_name: str | None = ""     # ERP: description
    material: str | None = ""         # ERP: caizhi
    image_url: str | None = ""        # ERP: FileUrl
    color: str | None = ""            # ERP: color
    unit: str | None = ""             # ERP: dw
    qty: float | None = 0             # ERP: sl
    sale_price: float | None = 0      # ERP: xsprice
    cost_price: float | None = 0      # ERP: cbprice
    amount: float | None = 0          # ERP: je
    in_transit_qty: float | None = 0  # ERP: ztsl
    sizes: list[SizeQty] = []         # from chimadetail


class InventoryResponse(BaseModel):
    total: int
    rows: list[InventoryItem]
