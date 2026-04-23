from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from app.client.erp_client import ERPClient
from app.dependencies import get_erp_client
from app.exceptions import AppException
from app.schemas.base import ProductListResponse

router = APIRouter(prefix="/api", tags=["base"])


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
