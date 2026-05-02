from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class ERPSizeDetail(BaseModel):
    model_config = ConfigDict(extra="ignore")
    field: str = ""     # size name (S, M, L, XL, ...)
    value: float | None = 0


class ERPWfhSizeDetail(BaseModel):
    """未发货尺码明细，比普通尺码多 fhvalue/thvalue/wfhvalue。"""
    model_config = ConfigDict(extra="ignore")
    field: str = ""
    value: float | None = 0       # 订单数量
    fhvalue: float | None = 0     # 已发货数量
    thvalue: float | None = 0     # 退货数量
    wfhvalue: float | None = 0    # 未发货数量


class ERPUnshippedReportRow(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str = ""
    dh: str = ""                     # 订单号
    zhdate: str = ""                 # 订单日期
    khid: str = ""                   # 客户编号
    khtype: str | None = ""          # 客户类型
    ddh: str | None = ""             # 客户订单号
    spbh: str | None = ""            # 品牌
    bbreed_main: str | None = ""     # 主货号
    huohao: str = ""                 # 货号
    huohaotype: str | None = ""      # 货号类别
    huohaoguige: str | None = ""     # 货号规格
    spname: str | None = ""          # 品名
    color: str | None = ""           # 颜色
    dw: str | None = ""              # 单位
    zsl: float | None = 0            # 订单数量
    fhsl: float | None = 0           # 发货数量
    thsl: float | None = 0           # 退货数量
    wfhsl: float | None = 0          # 未发货数量
    wfhje: float | None = 0          # 未发货金额
    kcsl: float | None = 0           # 库存数量
    price: float | None = 0          # 销售单价
    cbprice: float | None = 0        # 成本价
    dp_price: float | None = 0       # 吊牌价
    price_zk: float | None = 0       # 折扣单价
    gh_price: float | None = None    # 供货价
    zhuser: str | None = ""          # 制单人
    remark: str | None = ""          # 明细备注
    remark_main: str | None = ""     # 主备注
    bzfs: str | None = ""            # 包装方式
    khhh: str | None = ""            # 客户货号
    ywy: str | None = ""             # 业务员
    sfwg: int | None = 0             # 是否手动完工

    chimadetail: list[ERPSizeDetail] | None = []       # 订单尺码明细
    wfhchimadetail: list[ERPWfhSizeDetail] | None = [] # 未发货尺码明细
    kcchimadetail: list[ERPSizeDetail] | None = []     # 库存尺码明细
