from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class LoginResult(BaseModel):
    account_set_name: str
    qrcode: str
    project_url: str | None = None
    login_rs: str


class ProductListResponse(BaseModel):
    total: int
    rows: list[dict[str, Any]]
