"""ERP 销售订单同步 — 配置 & 同步 API 路由"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

import httpx
from fastapi import APIRouter, Depends, File, Request, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.services.erp_health import refresh_erp_health_status
from app.services.erp_sync import (
    get_erp_sync_config,
    get_sync_status,
    save_erp_sync_config,
    sync_products,
    sync_sales_orders,
    sync_sales_shipments,
)

router = APIRouter(tags=["ERP-同步"])


async def _refresh_erp_status_safely() -> None:
    try:
        await refresh_erp_health_status()
    except Exception:
        pass


# ---------- 配置 ----------

class ErpSyncConfigPayload(BaseModel):
    erp_base_url: Optional[str] = None
    erp_username: Optional[str] = None
    erp_password: Optional[str] = None
    erp_qr_image_path: Optional[str] = None
    sync_interval_minutes: Optional[int] = None
    sync_days_back: Optional[int] = None
    sync_enabled: Optional[bool] = None


class ErpConnectionTestPayload(BaseModel):
    erp_base_url: str
    erp_username: str
    erp_password: str
    erp_qr_image_path: str


async def _load_qr_image_bytes(qr_source: str) -> tuple[str, bytes]:
    qr_source = (qr_source or "").strip()
    if not qr_source:
        raise ValueError("未配置账套二维码图片")

    if qr_source.startswith(("http://", "https://")):
        from app.utils.oss_client import oss_client

        object_name = oss_client.parse_object_name(qr_source)
        if not object_name:
            raise ValueError("无法解析二维码 OSS 路径")
        img_bytes = oss_client.download_file(object_name)
        filename = qr_source.rsplit("/", 1)[-1].split("?")[0] or "qr.jpg"
        return filename, img_bytes

    qr_path = Path(qr_source)
    if not qr_path.is_absolute():
        qr_path = Path(__file__).resolve().parents[2] / qr_path
    if not qr_path.is_file():
        raise ValueError(f"二维码图片不存在: {qr_path}")
    return qr_path.name, qr_path.read_bytes()


@router.post("/test-connection", summary="测试 ERP 连接")
async def api_test_connection(payload: ErpConnectionTestPayload) -> dict[str, Any]:
    base_url = (payload.erp_base_url or "").strip().rstrip("/")
    username = (payload.erp_username or "").strip()
    password = (payload.erp_password or "").strip()
    qr_source = (payload.erp_qr_image_path or "").strip()

    if not base_url:
        return {"code": 400, "message": "请填写 ERP 服务地址"}
    if not username or not password:
        return {"code": 400, "message": "请填写 ERP 登录账号和密码"}
    if not qr_source:
        return {"code": 400, "message": "请先上传账套二维码"}

    try:
        filename, img_bytes = await _load_qr_image_bytes(qr_source)
    except Exception as exc:
        return {"code": 400, "message": f"读取二维码失败: {exc}"}

    try:
        async with httpx.AsyncClient(timeout=30, follow_redirects=True, trust_env=False) as client:
            account_set_resp = await client.post(
                f"{base_url}/Login/CheckAccountSet",
                headers={
                    "X-Requested-With": "XMLHttpRequest",
                    "Accept": "application/json, text/javascript, */*; q=0.01",
                },
                files={"imgData": (filename, img_bytes, "image/jpeg")},
            )

            if account_set_resp.status_code >= 400:
                return {"code": 502, "message": f"获取账套信息失败: HTTP {account_set_resp.status_code}"}

            account_set_payload = account_set_resp.json()
            if not account_set_payload.get("Success"):
                return {"code": 502, "message": account_set_payload.get("Message") or "获取账套信息失败"}

            account_set_data = account_set_payload.get("Data") or {}
            qrcode = account_set_data.get("qrcode")
            if not qrcode:
                return {"code": 502, "message": "获取账套信息失败: 缺少 qrcode"}

            login_resp = await client.post(
                f"{base_url}/Login/CheckLogin",
                headers={"Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"},
                data={"Account": username, "Password": password, "qrcode": qrcode},
            )

            if login_resp.status_code >= 400:
                return {"code": 502, "message": f"登录失败: HTTP {login_resp.status_code}"}

            login_payload = login_resp.json()
            login_rs = str(login_payload.get("rs", ""))
            if login_rs != "3":
                return {"code": 502, "message": f"登录失败, rs={login_rs}"}

            return {
                "code": 200,
                "message": "连接测试成功",
                "data": {
                    "account_set_name": account_set_data.get("accountSetName", ""),
                    "project_url": account_set_data.get("projectURL"),
                    "login_rs": login_rs,
                },
            }
    except Exception as exc:
        return {"code": 502, "message": f"连接测试失败: {exc}"}


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
    await _refresh_erp_status_safely()
    return {"code": 200, "message": "配置已保存", "data": cfg}


# ---------- 账套二维码上传 ----------

@router.post("/upload-qr", summary="上传账套二维码图片到 OSS")
async def api_upload_qr(
    file: UploadFile = File(...),
    request: Request = None,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    import logging
    import uuid

    logger = logging.getLogger(__name__)
    content = await file.read()
    ext = file.filename.rsplit(".", 1)[-1] if "." in file.filename else "jpg"
    object_name = f"erp/qr/{uuid.uuid4().hex}.{ext}"

    try:
        from app.utils.oss_client import oss_client
        content_type = file.content_type or "image/jpeg"
        url = oss_client.upload_file(object_name, content, content_type=content_type)
    except Exception as exc:
        logger.exception("[ERP Sync] OSS 上传失败")
        return {"code": 500, "message": f"OSS 上传失败: {exc}"}

    if not url:
        return {"code": 500, "message": "OSS 上传返回空 URL，请检查 OSS 配置"}

    # 存入配置
    save_erp_sync_config(db, {"erp_qr_image_path": url})
    # 热更新 ncloud config
    from app.services.erp_sync import reload_erp_client
    await reload_erp_client(request.app)
    await _refresh_erp_status_safely()
    return {"code": 200, "message": "上传成功", "data": {"url": url}}


# ---------- 账套二维码代理（需登录） ----------

@router.get("/qr-image", summary="获取账套二维码图片（从 MinIO 代理）")
def api_get_qr_image(db: Session = Depends(get_db)):
    """前端通过此接口获取二维码预览，无需 MinIO 公开访问权限"""
    import logging
    logger = logging.getLogger(__name__)
    cfg = get_erp_sync_config(db)
    url = cfg.get("erp_qr_image_path") or ""
    if not url:
        return Response(status_code=404, content=b"No QR image configured")

    from app.utils.oss_client import oss_client
    object_name = oss_client.parse_object_name(url)
    if not object_name:
        return Response(status_code=404, content=b"Invalid QR image URL")

    try:
        img_bytes = oss_client.download_file(object_name)
    except Exception as exc:
        logger.warning("[ERP Sync] 下载二维码图片失败: %s", exc)
        return Response(status_code=500, content=b"Failed to fetch QR image")

    # 根据扩展名推断 content-type
    ext = object_name.rsplit(".", 1)[-1].lower() if "." in object_name else "jpg"
    ct_map = {"png": "image/png", "gif": "image/gif", "webp": "image/webp", "bmp": "image/bmp"}
    content_type = ct_map.get(ext, "image/jpeg")
    return Response(content=img_bytes, media_type=content_type)


# ---------- 同步 ----------

@router.get("/status", summary="查询同步状态")
def api_sync_status() -> dict[str, Any]:
    return {"code": 200, "data": get_sync_status()}


@router.post("/trigger", summary="手动触发全量同步")
async def api_sync_trigger(request: Request, days_back: int = 90) -> dict[str, Any]:
    try:
        erp_client = request.app.state.erp_client
        orders_result = await sync_sales_orders(erp_client, days_back=days_back)
        shipments_result = await sync_sales_shipments(erp_client, days_back=days_back)
        products_result = await sync_products(erp_client)
        return {"code": 200, "message": "同步完成", "data": {
            "orders": orders_result,
            "shipments": shipments_result,
            "products": products_result,
        }}
    finally:
        await _refresh_erp_status_safely()


@router.post("/trigger-orders", summary="手动触发销售订单同步")
async def api_sync_orders_trigger(request: Request, days_back: int = 90) -> dict[str, Any]:
    try:
        erp_client = request.app.state.erp_client
        result = await sync_sales_orders(erp_client, days_back=days_back)
        return {"code": 200, "message": "订单同步完成", "data": result}
    finally:
        await _refresh_erp_status_safely()


@router.post("/trigger-shipments", summary="手动触发发货单同步")
async def api_sync_shipments_trigger(request: Request, days_back: int = 90) -> dict[str, Any]:
    try:
        erp_client = request.app.state.erp_client
        result = await sync_sales_shipments(erp_client, days_back=days_back)
        return {"code": 200, "message": "发货单同步完成", "data": result}
    finally:
        await _refresh_erp_status_safely()


@router.post("/trigger-products", summary="手动触发产品同步")
async def api_sync_products_trigger(request: Request) -> dict[str, Any]:
    try:
        erp_client = request.app.state.erp_client
        result = await sync_products(erp_client)
        return {"code": 200, "message": "产品同步完成", "data": result}
    finally:
        await _refresh_erp_status_safely()
