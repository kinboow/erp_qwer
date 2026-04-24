from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class SizeQty(BaseModel):
    size: str
    qty: int


class SalesOrderListItem(BaseModel):
    state: int                        # ERP: state
    print_count: int = 0              # ERP: printnum
    order_no: str                     # ERP: dh
    order_date: str                   # ERP: zhdate
    creator: str | None = ""          # ERP: zhuser
    customer_id: str                  # ERP: khid
    customer_name: str | None = ""    # ERP: khname
    customer_tel: str | None = ""     # ERP: khtel
    customer_addr: str | None = ""    # ERP: khaddr
    product_no: str | None = ""       # ERP: huohao_mx
    total_amount: float | None = 0    # ERP: je_sum
    total_qty: float | None = 0       # ERP: sl_sum
    salesperson: str | None = ""      # ERP: ywy


class SalesOrderListResponse(BaseModel):
    total: int
    rows: list[SalesOrderListItem]


class SalesOrderDetailRow(BaseModel):
    erp_item_id: str | None = "" # ERP: id (GUID)
    brand: str                   # ERP: spbh
    product_no: str              # ERP: huohao
    sizes: list[SizeQty]         # from chimadetail
    grade: str | None = ""             # ERP: khgrade
    customer_product_no: str | None = ""  # ERP: khhh
    product_name: str | None = ""      # ERP: spname
    packaging: str | None = ""         # ERP: bzfs
    color: str | None = ""             # ERP: color
    price: float | None = 0            # ERP: price
    discount: int | None = 100         # ERP: zk
    unit: str | None = ""              # ERP: dw
    remark: str | None = ""            # ERP: remark


class SalesOrderMainInfo(BaseModel):
    order_no: str                # ERP: dh
    order_date: str              # ERP: zhdate
    customer_id: str             # ERP: khid
    customer_name: str | None = None  # ERP: khname (may be absent in detail response)
    state: int                   # ERP: state
    total_qty: float | None = 0  # ERP: sl_sum
    total_amount: float | None = 0  # ERP: je_sum
    creator: str | None = ""           # ERP: zhuser
    customer_tel: str | None = ""      # ERP: khtel
    customer_addr: str | None = ""     # ERP: khaddr
    salesperson: str | None = ""       # ERP: ywy
    shipping_method: str | None = ""   # ERP: tyfs
    shipping_tel: str | None = ""      # ERP: shtel
    shipping_addr: str | None = ""     # ERP: shaddr
    order_ref: str | None = ""         # ERP: ddh
    delivery_date: str | None = ""     # ERP: jh_date
    plan: str | None = ""              # ERP: sfplan
    currency: str | None = ""          # ERP: bizhong
    price_print: int | None = None     # ERP: price_print
    payment_amount: float | None = None  # ERP: fkje
    brand: str | None = ""             # ERP: main_spbh
    customer_type: str | None = ""     # ERP: khtype
    contact_person: str | None = ""    # ERP: link_man
    discount_amount: float | None = None  # ERP: yhje
    remark: str | None = ""      # ERP: remark


class SalesOrderDetail(BaseModel):
    main: SalesOrderMainInfo
    detail: list[SalesOrderDetailRow]


# --- Write schemas ---


class CreateOrderDetailRow(BaseModel):
    brand: str = ""                          # ERP: spbh
    product_no: str                          # ERP: huohao (required)
    color: str = ""                          # ERP: color
    sizes: list[SizeQty]                     # → chimadetail
    unit: str = ""                           # ERP: dw
    price: float = 0                         # ERP: price
    discount: int = 100                      # ERP: zk
    packaging: str = ""                      # ERP: bzfs
    customer_product_no: str = ""            # ERP: khhh
    grade: str = ""                          # ERP: khgrade
    product_spec: str = ""                   # ERP: huohaoguige (货号规格)
    semi_product_no: str = ""                # ERP: bcp_huohao (半成品货号)
    linked_order_ref: str = ""               # ERP: d_ddh (关联订单号)
    remark: str = ""


class CreateSalesOrderRequest(BaseModel):
    customer_id: str = Field(..., description="客户编号 (ERP: khid)")
    order_date: str = Field(..., description="订单日期 YYYY-MM-DD HH:mm:ss")
    customer_addr: str = ""
    customer_tel: str = ""
    shipping_addr: str = ""
    shipping_tel: str = ""
    shipping_method: str = ""
    salesperson: str = ""
    order_ref: str = ""                      # ERP: ddh (客户自定义订单号)
    currency: str = ""
    brand: str = ""                          # ERP: main_spbh
    customer_type: str = ""
    delivery_date: str = ""                  # ERP: jh_date (交货日期)
    contact_person: str = ""                 # ERP: link_man (联系人)
    plan: str = "否"                         # ERP: sfplan (下计划 是/否，设"是"时 ERP 可能要求 order_ref 非空)
    price_print: int = 1                     # ERP: price_print (单价打印 0=否 1=是)
    payment_amount: float | None = None      # ERP: fkje (收款金额，未完整测试——完整收款功能需配合 fkData)
    remark: str = ""
    detail: list[CreateOrderDetailRow] = Field(..., min_length=1)


class UpdateSalesOrderRequest(BaseModel):
    customer_id: str | None = None
    order_date: str | None = None
    customer_addr: str | None = None
    customer_tel: str | None = None
    shipping_addr: str | None = None
    shipping_tel: str | None = None
    shipping_method: str | None = None
    salesperson: str | None = None
    order_ref: str | None = None
    currency: str | None = None
    brand: str | None = None
    customer_type: str | None = None
    delivery_date: str | None = None         # ERP: jh_date
    contact_person: str | None = None        # ERP: link_man
    plan: str | None = None                  # ERP: sfplan
    price_print: int | None = None           # ERP: price_print
    payment_amount: float | None = None      # ERP: fkje (未完整测试)
    remark: str | None = None
    detail: list[CreateOrderDetailRow] | None = None


class AuditAction(str, Enum):
    audit = "audit"
    unaudit = "unaudit"
    void = "void"


class AuditActionRequest(BaseModel):
    action: AuditAction


class WriteOperationResponse(BaseModel):
    dh: str
    message: str
    state: int | None = None
