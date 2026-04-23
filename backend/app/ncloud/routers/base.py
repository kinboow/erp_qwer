from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from app.ncloud.client.erp_client import ERPClient
from app.ncloud.dependencies import get_erp_client
from app.ncloud.exceptions import AppException
from app.ncloud.schemas.base import CustomerListResponse, ProductListResponse
from app.ncloud.services.base import list_customers

router = APIRouter(tags=["base"])


def _guard_payload(payload: dict[str, Any]) -> dict[str, Any]:
    if "rows" not in payload or "total" not in payload:
        raise HTTPException(
            status_code=502,
            detail={"message": "上游返回结构异常", "payload": payload},
        )
    return payload


@router.get("/products", response_model=ProductListResponse)
async def api_products(
    page: int = Query(default=1, ge=1),
    rows: int = Query(default=20, ge=1, le=500),
    erp: ERPClient = Depends(get_erp_client),
) -> dict[str, Any]:
    try:
        payload = await erp.post_form(
            "/BaseInfo/SysHuohao/GridPageListJson",
            {"page": page, "rows": rows},
        )
        return _guard_payload(payload)
    except AppException:
        raise
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/customers", response_model=CustomerListResponse)
async def api_customers(
    page: int = Query(default=1, ge=1),
    rows: int = Query(default=20, ge=1, le=500),
    search: str | None = Query(default=None),
    erp: ERPClient = Depends(get_erp_client),
) -> CustomerListResponse:
    try:
        return await list_customers(erp, page=page, rows=rows, search=search)
    except AppException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
