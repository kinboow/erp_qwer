"""ERP 销售订单同步 — 配置 & 同步 API 路由"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.services.erp_sync import (
    get_erp_sync_config,
    get_sync_status,
    save_erp_sync_config,
    sync_sales_orders,
)

router = APIRouter(tags=["ERP-同步"])


# ---------- 配置 ----------

class ErpSyncConfigPayload(BaseModel):
    erp_base_url: Optional[str] = None
    erp_username: Optional[str] = None
    erp_password: Optional[str] = None
    erp_qr_image_path: Optional[str] = None
    sync_interval_minutes: Optional[int] = None
    sync_days_back: Optional[int] = None
    sync_enabled: Optional[bool] = None


@router.get("/config", summary="获取 ERP 同步配置")
def api_get_config(db: Session = Depends(get_db)) -> dict[str, Any]:
    cfg = get_erp_sync_config(db)
    return {"code": 200, "data": cfg}


@router.put("/config", summary="保存 ERP 同步配置")
async def api_save_config(
    payload: ErpSyncConfigPayload,
    request: Request,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    cfg = save_erp_sync_config(db, payload.model_dump(exclude_none=True))
    # 重新加载配置到 app.state
    from app.services.erp_sync import reload_erp_client, restart_sync_scheduler
    await reload_erp_client(request.app)
    restart_sync_scheduler(request.app)
    return {"code": 200, "message": "配置已保存", "data": cfg}


# ---------- 同步 ----------

@router.get("/status", summary="查询同步状态")
def api_sync_status() -> dict[str, Any]:
    return {"code": 200, "data": get_sync_status()}


@router.post("/trigger", summary="手动触发同步")
async def api_sync_trigger(request: Request, days_back: int = 90) -> dict[str, Any]:
    erp_client = request.app.state.erp_client
    result = await sync_sales_orders(erp_client, days_back=days_back)
    return {"code": 200, "message": "同步完成", "data": result}
