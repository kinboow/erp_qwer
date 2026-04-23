from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class ERPInventorySizeDetail(BaseModel):
    model_config = ConfigDict(extra="ignore")
    field: str = ""     # size name
    value: int | None = 0


class ERPInventoryRow(BaseModel):
    model_config = ConfigDict(extra="ignore")

    ck: str = ""                        # 仓库编号
    huohaotypename: str | None = ""     # 货号类别
    huohao: str = ""                    # 货号
    description: str | None = ""        # 品名
    caizhi: str | None = ""             # 材质
    FileUrl: str | None = ""            # 图片 URL
    color: str | None = ""              # 颜色
    dw: str | None = ""                 # 单位
    sl: float | None = 0                # 库存数量
    xsprice: float | None = 0           # 销售价
    cbprice: float | None = 0           # 成本价
    je: float | None = 0                # 金额
    ztsl: float | None = 0              # 生产在途数

    chimadetail: list[ERPInventorySizeDetail] = []
