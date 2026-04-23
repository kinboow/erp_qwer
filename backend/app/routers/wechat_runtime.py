from fastapi import APIRouter, Body, Depends, Query
from pydantic import BaseModel
from typing import Optional
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User
from app.dependencies import get_current_user
from app.services.wechat_runtime_compat import ingest_runtime_message
from app.services.wechat_ws_service import wechat_ws_service

router = APIRouter(tags=["企业微信运行时"])


class WechatWsConnectPayload(BaseModel):
    instanceId: str
    url: str


def json_response(code=200, message="success", data=None):
    resp = {"code": code, "message": message}
    if data is not None:
        resp["data"] = data
    return resp


@router.api_route("/callback/http", methods=["GET", "POST"], summary="接收企业微信 HTTP 回调")
async def receive_http_callback(
    body: Optional[dict] = Body(default=None),
    instanceId: Optional[str] = Query(None),
    wxid: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    data = await ingest_runtime_message(
        db,
        body or {},
        source="http_callback",
        instance_id=instanceId,
        wxid=wxid,
    )
    return json_response(message="回调接收成功", data=data)


@router.api_route("/sync", methods=["GET", "POST"], summary="兼容 NGCBot HTTP 回调")
async def receive_sync_callback(
    body: Optional[dict] = Body(default=None),
    wxid: Optional[str] = Query(None),
    instanceId: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    data = await ingest_runtime_message(
        db,
        body or {},
        source="http_callback",
        instance_id=instanceId,
        wxid=wxid,
    )
    return json_response(message="回调接收成功", data=data)


@router.get("/ws/status", summary="获取企业微信 WS 状态")
async def get_ws_status(
    instanceId: Optional[str] = Query(None),
    current_user: User = Depends(get_current_user)
):
    return json_response(data=wechat_ws_service.get_status(instanceId))


@router.post("/ws/connect", summary="启动企业微信 WS 连接")
async def connect_ws(
    payload: WechatWsConnectPayload,
    current_user: User = Depends(get_current_user)
):
    result = await wechat_ws_service.connect(payload.instanceId, payload.url)
    return json_response(message="WebSocket 连接已启动", data=result)


@router.delete("/ws/connect/{instance_id}", summary="关闭企业微信 WS 连接")
async def disconnect_ws(
    instance_id: str,
    current_user: User = Depends(get_current_user)
):
    ok = await wechat_ws_service.disconnect(instance_id)
    return json_response(message="WebSocket 连接已关闭" if ok else "未找到对应连接")
