from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class ERPSizeDetail(BaseModel):
    model_config = ConfigDict(extra="ignore")
    field: str = ""    # size name (e.g. "XL", "2XL") — ERP key is "field"
    value: int | None = 0     # quantity (null = no qty for this size)


class ERPOrderDetailRow(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str | None = ""          # ERP GUID for this detail row
    spbh: str = ""        # brand/product code
    huohao: str = ""      # product number (货号)
    chimadetail: list[ERPSizeDetail] = []
    khgrade: str | None = ""     # grade
    khhh: str | None = ""        # customer product no
    spname: str | None = ""      # product name
    bzfs: str | None = ""        # packaging
    color: str | None = ""       # color
    price: float | None = 0      # price
    zk: int | None = 100         # discount
    dw: str | None = ""          # unit
    remark: str | None = ""      # remark


class ERPOrderMain(BaseModel):
    model_config = ConfigDict(extra="ignore")
    dh: str = ""          # order number
    zhdate: str | None = ""      # order date
    khid: str = ""        # customer ID
    khname: str | None = ""  # customer name (may be absent in detail response)
    state: int = 0        # status: 0=draft, 1=approved
    sl_sum: float | None = 0     # total quantity
    je_sum: float | None = 0     # total amount
    remark: str | None = ""      # remarks
    zhuser: str | None = ""      # creator
    khtel: str | None = ""       # customer tel
    khaddr: str | None = ""      # customer address
    ywy: str | None = ""         # salesperson
    tyfs: str | None = ""        # shipping method
    shtel: str | None = ""       # shipping tel
    shaddr: str | None = ""      # shipping address
    ddh: str | None = ""         # order ref
    jh_date: str | None = ""     # delivery date
    sfplan: str | None = ""      # plan
    bizhong: str | None = ""     # currency
    price_print: int | None = None  # price print
    fkje: float | None = None    # payment amount
    main_spbh: str | None = ""   # brand
    khtype: str | None = ""      # customer type
    link_man: str | None = ""    # contact person
    yhje: float | None = None    # discount amount


class ERPOrderListRow(BaseModel):
    model_config = ConfigDict(extra="ignore")
    dh: str = ""              # order number
    zhdate: str | None = ""          # order date
    khid: str = ""            # customer ID
    khname: str | None = ""   # customer name
    khaddr: str | None = ""   # customer address
    khtel: str | None = ""    # customer phone
    state: int = 0            # status
    printnum: int = 0         # print count
    huohao_mx: str | None = ""  # product number summary
    je_sum: float | None = 0    # total amount
    sl_sum: float | None = 0    # total quantity
    zhuser: str | None = ""   # creator
    ywy: str | None = ""      # salesperson


class ERPOrderDetail(BaseModel):
    model_config = ConfigDict(extra="ignore")
    main: ERPOrderMain = ERPOrderMain()
    detail: list[ERPOrderDetailRow] = []
