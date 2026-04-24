from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class LoginResult(BaseModel):
    account_set_name: str
    qrcode: str
    project_url: str | None = None
    login_rs: str


class ProductListItem(BaseModel):
    product_id: str = ""
    product_no: str = ""          # 货号
    product_name: str | None = ""  # 品名
    brand: str | None = ""         # 品牌/编号
    category: str | None = ""      # 货号类别
    color: str | None = ""         # 颜色
    unit: str | None = ""          # 单位
    price: float | None = 0        # 单价
    spec: str | None = ""          # 规格
    material: str | None = ""      # 材质
    image_url: str | None = ""     # 图片
    remark: str | None = ""        # 备注


class ProductListResponse(BaseModel):
    total: int
    rows: list[ProductListItem]


class CustomerListItem(BaseModel):
    customer_id: str
    customer_name: str | None = ""
    short_code: str | None = ""
    address: str | None = ""
    phone: str | None = ""
    telephone: str | None = ""
    shipping_address: str | None = ""
    shipping_phone: str | None = ""
    contact_person: str | None = ""
    state: int | None = None
    nature: list[str] = Field(default_factory=list)
    credit_limit: float | None = None
    salesperson: str | None = ""
    customer_type: str | None = ""
    remark: str | None = ""


class CustomerListResponse(BaseModel):
    total: int
    rows: list[CustomerListItem]
