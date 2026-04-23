from __future__ import annotations

from pydantic import BaseModel, Field

from app.schemas.sales_orders import AuditAction, AuditActionRequest, SizeQty, WriteOperationResponse  # noqa: F401 — re-export for router


class ShipmentListItem(BaseModel):
    order_no: str          # ERP: dh
    order_date: str        # ERP: zhdate
    customer_id: str       # ERP: khid
    customer_addr: str | None = ""  # ERP: khaddr
    state: int             # ERP: state
    total_qty: float | None = 0  # ERP: fhzsl
    total_amount: float | None = 0  # ERP: je_sum
    tracking_no: str | None = ""  # ERP: yunhao
    customer_name: str | None = ""  # ERP: khname
    print_count: int = 0  # ERP: printnum
    salesperson: str | None = ""  # ERP: ywy
    shipping_addr: str | None = ""  # ERP: shaddr
    shipping_method: str | None = ""  # ERP: tyfs
    freight: float | None = None  # ERP: yunfei


class ShipmentListResponse(BaseModel):
    total: int
    rows: list[ShipmentListItem]


class ShipmentDetailRow(BaseModel):
    product_no: str        # ERP: huohao
    color: str | None = None  # ERP: color
    sizes: list[SizeQty]  # from chimadetail
    order_ref: str | None = ""  # ERP: ddid
    brand: str | None = ""  # ERP: spbh
    customer_product_no: str | None = ""  # ERP: khhh
    product_name: str | None = ""  # ERP: spname
    packaging: str | None = ""  # ERP: bzfs
    price: float | None = 0  # ERP: price
    discount: int | None = 100  # ERP: zk
    unit: str | None = ""  # ERP: dw
    remark: str | None = ""  # ERP: remark


class ShipmentMainInfo(BaseModel):
    order_no: str          # ERP: dh
    order_date: str        # ERP: zhdate
    customer_id: str       # ERP: khid
    customer_addr: str | None = ""  # ERP: khaddr
    state: int             # ERP: state
    warehouse: str | None = ""  # ERP: ck
    tracking_no: str | None = ""  # ERP: yunhao
    total_amount: float | None = 0  # ERP: je_sum
    remark: str | None = ""  # ERP: remark
    customer_name: str | None = ""  # ERP: khname
    creator: str | None = ""  # ERP: zhuser
    handler: str | None = ""  # ERP: jsr
    customer_tel: str | None = ""  # ERP: khtel
    shipping_method: str | None = ""  # ERP: tyfs
    shipping_tel: str | None = ""  # ERP: shtel
    shipping_addr: str | None = ""  # ERP: shaddr
    freight: float | None = None  # ERP: yunfei
    payment_amount: float | None = None  # ERP: fkje
    salesperson: str | None = ""  # ERP: ywy
    delivery_person: str | None = ""  # ERP: shuser
    customer_type: str | None = ""  # ERP: khtype
    currency: str | None = ""  # ERP: bizhong
    price_print: int | None = None  # ERP: price_print
    contact_person: str | None = ""  # ERP: link_man
    contact_tel: str | None = ""  # ERP: tel1
    total_qty: float | None = 0  # ERP: fhzsl


class ShipmentDetail(BaseModel):
    main: ShipmentMainInfo
    detail: list[ShipmentDetailRow]


# --- Write schemas ---


class CreateShipmentDetailRow(BaseModel):
    brand: str = ""                          # ERP: spbh
    product_no: str                          # ERP: huohao (required)
    color: str                               # ERP: color (required for shipments)
    sizes: list[SizeQty]                     # → chimadetail
    unit: str = ""                           # ERP: dw
    price: float = 0                         # ERP: price
    discount: int = 100                      # ERP: zk
    packaging: str = ""                      # ERP: bzfs
    customer_product_no: str = ""            # ERP: khhh
    order_ref_id: str | None = None          # ERP: ddid (关联销售订单行ID)
    product_spec: str = ""                   # ERP: huohaoguige (货号规格)
    semi_product_no: str = ""                # ERP: bcp_huohao (半成品货号)
    material: str = ""                       # ERP: caizhi (材质)
    remark: str = ""


class CreateShipmentRequest(BaseModel):
    customer_id: str = Field(..., description="客户编号 (ERP: khid)")
    shipment_date: str = Field(..., description="发货日期 YYYY-MM-DD HH:mm:ss")
    warehouse: str = Field(..., description="发货仓库编号 (ERP: ck)")
    customer_addr: str = ""
    shipping_addr: str = ""
    shipping_tel: str = ""
    shipping_method: str = ""
    delivery_person: str = ""                # ERP: shuser
    tracking_no: str = ""                    # ERP: yunhao
    freight: float | None = None             # ERP: yunfei
    salesperson: str = ""
    contact_person: str = ""                 # ERP: link_man
    contact_tel: str = ""                    # ERP: tel1
    currency: str = ""
    customer_type: str = ""
    handler: str = ""                        # ERP: jsr (经手人)
    price_print: int = 1                     # ERP: price_print (单价打印 0=否 1=是)
    payment_amount: float | None = None      # ERP: fkje (收款金额，未完整测试——完整收款功能需配合 fkData)
    remark: str = ""
    detail: list[CreateShipmentDetailRow] = Field(..., min_length=1)


class UpdateShipmentRequest(BaseModel):
    customer_id: str | None = None
    shipment_date: str | None = None
    warehouse: str | None = None
    customer_addr: str | None = None
    shipping_addr: str | None = None
    shipping_tel: str | None = None
    shipping_method: str | None = None
    delivery_person: str | None = None
    tracking_no: str | None = None
    freight: float | None = None
    salesperson: str | None = None
    contact_person: str | None = None
    contact_tel: str | None = None
    currency: str | None = None
    customer_type: str | None = None
    handler: str | None = None               # ERP: jsr
    price_print: int | None = None           # ERP: price_print
    payment_amount: float | None = None      # ERP: fkje (未完整测试)
    remark: str | None = None
    detail: list[CreateShipmentDetailRow] | None = None
