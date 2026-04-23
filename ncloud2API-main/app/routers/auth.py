from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from app.client.erp_client import ERPClient
from app.dependencies import get_erp_client
from app.exceptions import AppException
from app.schemas.base import LoginResult

router = APIRouter(prefix="/api", tags=["auth"])


@router.post("/login", response_model=LoginResult)
async def api_login(erp: ERPClient = Depends(get_erp_client)) -> LoginResult:
    try:
        await erp._auth.login(force=True)
        account_set = erp._auth._last_account_set or {}
        return LoginResult(
            account_set_name=account_set.get("account_set_name", ""),
            qrcode=account_set.get("qrcode", ""),
            project_url=account_set.get("project_url"),
            login_rs="3",
        )
    except AppException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/account-set")
async def api_account_set(erp: ERPClient = Depends(get_erp_client)) -> dict[str, Any]:
    try:
        return await erp._auth.resolve_account_set()
    except AppException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
