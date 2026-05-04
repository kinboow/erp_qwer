import asyncio
import json
import mimetypes
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.models import User
from sqlalchemy import text

from app.services.downstream_orders import (
    approve_review,
    check_duplicate_order,
    create_review_from_callback,
    get_review_attachment_debug,
    get_review_context_messages,
    get_review_detail,
    list_reviews,
    manual_order,
    parse_review_content,
    replace_old_order,
    retry_review_attachment_download,
    revert_to_pending,
    void_review,
)
from app.services.review_events import subscribe
from app.utils.oss_client import oss_client

router = APIRouter(tags=["下游客户订单审核"])


class CallbackIngestPayload(BaseModel):
    instanceId: Optional[str] = None
    payload: dict[str, Any]


class ReviewApprovePayload(BaseModel):
    customer_id: int
    review_note: Optional[str] = ""


class ReviewManualPayload(BaseModel):
    customer_id: int
    order_data: dict[str, Any]
    review_note: Optional[str] = ""


class ReviewVoidPayload(BaseModel):
    review_note: Optional[str] = ""


class CheckDuplicatePayload(BaseModel):
    customer_id: int
    order_data: Optional[dict[str, Any]] = None


class ReviewAttachmentRetryPayload(BaseModel):
    reparse: Optional[bool] = True
    force_download: Optional[bool] = False


def json_response(code=200, message="success", data=None):
    result = {"code": code, "message": message}
    if data is not None:
        result["data"] = data
    return result


@router.get("/reviews", summary="获取待审核订单列表")
def get_reviews(
    page: int = Query(1, ge=1),
    pageSize: int = Query(20, ge=1, le=100),
    review_status: Optional[str] = Query(None),
    customer_id: Optional[int] = Query(None),
    sort: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    data = list_reviews(db, page=page, page_size=pageSize, review_status=review_status or "", customer_id=customer_id, sort=sort)
    return json_response(data=data)


@router.get("/reviews/stream", summary="SSE 实时推送审核单变动")
async def review_stream(request: Request):
    """Server-Sent Events 端点，AI解析完成后实时推送通知"""
    async def event_generator():
        try:
            async for payload in subscribe():
                if await request.is_disconnected():
                    break
                data = json.dumps(payload, ensure_ascii=False)
                yield f"data: {data}\n\n"
        except asyncio.CancelledError:
            pass

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )


@router.get("/media/{msg_log_id}", summary="获取消息媒体文件")
def get_media_file(
    msg_log_id: int,
    token: Optional[str] = Query(None, description="JWT token（用于浏览器直接访问）"),
    db: Session = Depends(get_db),
):
    """从 OSS 获取消息关联的媒体文件（图片/文件），支持 Bearer 或 query token 鉴权"""
    from app.utils.security import decode_access_token
    from app.utils.redis_client import redis_client as _redis
    # 尝试从 Authorization header 获取 token
    _token = token
    if not _token:
        raise HTTPException(status_code=401, detail="缺少认证凭证")
    if _redis.exists(f"blacklist:{_token}"):
        raise HTTPException(status_code=401, detail="令牌已失效")
    payload = decode_access_token(_token)
    if not payload or not payload.get("user_id"):
        raise HTTPException(status_code=401, detail="无效的认证凭证")

    row = db.execute(text(
        "SELECT oss_key, message_type, content_preview FROM message_logs WHERE id = :id"
    ), {"id": msg_log_id}).mappings().first()
    if not row or not row.get("oss_key"):
        raise HTTPException(status_code=404, detail="媒体文件不存在或尚未归档")
    try:
        file_bytes = oss_client.download_file(row["oss_key"])
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"OSS 下载失败: {exc}") from exc
    ct, _ = mimetypes.guess_type(row["oss_key"])
    if not ct:
        msg_type = str(row.get("message_type") or "").lower()
        ct = "image/png" if msg_type in ("image", "img", "picture") else "application/octet-stream"
    return Response(content=file_bytes, media_type=ct, headers={"Cache-Control": "max-age=86400"})


@router.get("/reviews/{review_id}", summary="获取待审核订单详情")
def get_review(
    review_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        data = get_review_detail(db, review_id)
        return json_response(data=data)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/reviews/ingest", summary="写入企微回调消息为待审核订单")
async def ingest_review(
    payload: CallbackIngestPayload,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    data = await create_review_from_callback(db, payload.payload, payload.instanceId)
    return json_response(message="消息已写入待审核", data=data)


@router.post("/reviews/{review_id}/reparse", summary="重新解析待审核订单")
async def reparse_review(
    review_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        data = await parse_review_content(db, review_id)
        return json_response(message="重新解析成功", data=data)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/reviews/{review_id}/context-messages", summary="获取审核记录上下文聊天消息")
def get_review_context_messages_api(
    review_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        data = get_review_context_messages(db, review_id)
        return json_response(data=data)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/reviews/{review_id}/attachment-debug", summary="查看附件下载调试信息")
def get_review_attachment_debug_api(
    review_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        data = get_review_attachment_debug(db, review_id)
        return json_response(data=data)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/reviews/{review_id}/attachment-download", summary="手动重试附件下载")
async def retry_review_attachment_download_api(
    review_id: int,
    payload: ReviewAttachmentRetryPayload,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        data = await retry_review_attachment_download(
            db,
            review_id,
            reparse=bool(payload.reparse),
            force_download=bool(payload.force_download),
        )
        return json_response(message="附件下载处理完成", data=data)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/reviews/{review_id}/check-duplicate", summary="下单前检查重复订单")
def check_duplicate_api(
    review_id: int,
    payload: CheckDuplicatePayload,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        duplicates = check_duplicate_order(db, review_id, payload.customer_id, payload.order_data)
        return json_response(data={"duplicates": duplicates})
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/reviews/{review_id}/approve", summary="审核并下销售单")
async def approve_review_api(
    review_id: int,
    payload: ReviewApprovePayload,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        data = await approve_review(db, review_id, payload.customer_id, current_user, payload.review_note or "")
        return json_response(message="审核下单成功", data=data)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/reviews/{review_id}/replace", summary="替换旧单")
async def replace_review_api(
    review_id: int,
    payload: ReviewApprovePayload,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        data = await replace_old_order(db, review_id, payload.customer_id, current_user, payload.review_note or "")
        return json_response(message="替换旧单成功", data=data)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/reviews/{review_id}/manual", summary="手动录单")
async def manual_review_api(
    review_id: int,
    payload: ReviewManualPayload,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        data = await manual_order(db, review_id, payload.customer_id, payload.order_data, current_user, payload.review_note or "")
        return json_response(message="手动录单成功", data=data)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/reviews/{review_id}/void", summary="废单")
def void_review_api(
    review_id: int,
    payload: ReviewVoidPayload,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        data = void_review(db, review_id, current_user, payload.review_note or "")
        return json_response(message="已标记为废单", data=data)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/reviews/{review_id}/revert-pending", summary="废单转为待审核")
def revert_pending_api(
    review_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        data = revert_to_pending(db, review_id, current_user)
        return json_response(message="已转为待审核", data=data)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
