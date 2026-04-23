from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class LoginResult(BaseModel):
    account_set_name: str
    qrcode: str
    project_url: str | None = None
    login_rs: str


class ProductListResponse(BaseModel):
    total: int
    rows: list[dict[str, Any]]


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
