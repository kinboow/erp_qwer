from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class ERPShipmentSizeDetail(BaseModel):
    model_config = ConfigDict(extra="ignore")
    field: str = ""    # size name
    value: int | None = 0     # quantity (null = no qty for this size)


class ERPShipmentDetailRow(BaseModel):
    model_config = ConfigDict(extra="ignore")
    spbh: str = ""
    huohao: str = ""
    color: str | None = None
    chimadetail: list[ERPShipmentSizeDetail] = []
    ddid: str | None = ""
    khhh: str | None = ""
    spname: str | None = ""
    bzfs: str | None = ""
    price: float | None = 0
    zk: int | None = 100
    dw: str | None = ""
    remark: str | None = ""


class ERPShipmentMain(BaseModel):
    model_config = ConfigDict(extra="ignore")
    dh: str = ""
    zhdate: str = ""
    khid: str = ""
    khaddr: str | None = ""
    state: int = 0
    ck: str | None = ""         # warehouse
    yunhao: str | None = ""     # tracking number
    je_sum: float | None = 0    # total amount
    fhzsl: float | None = 0     # total shipment qty
    remark: str | None = ""
    khname: str | None = ""
    zhuser: str | None = ""
    jsr: str | None = ""
    khtel: str | None = ""
    tyfs: str | None = ""
    shtel: str | None = ""
    shaddr: str | None = ""
    yunfei: float | None = None
    fkje: float | None = None
    ywy: str | None = ""
    shuser: str | None = ""
    khtype: str | None = ""
    bizhong: str | None = ""
    price_print: int | None = None
    link_man: str | None = ""
    tel1: str | None = ""


class ERPShipmentDetail(BaseModel):
    model_config = ConfigDict(extra="ignore")
    main: ERPShipmentMain = ERPShipmentMain()
    detail: list[ERPShipmentDetailRow] = []


class ERPShipmentListRow(BaseModel):
    model_config = ConfigDict(extra="ignore")
    dh: str = ""
    zhdate: str = ""
    khid: str = ""
    khaddr: str | None = ""
    state: int = 0
    fhzsl: float | None = 0
    je_sum: float | None = 0
    yunhao: str | None = ""
    khname: str | None = ""
    printnum: int = 0
    ywy: str | None = ""
    shaddr: str | None = ""
    tyfs: str | None = ""
    yunfei: float | None = None
