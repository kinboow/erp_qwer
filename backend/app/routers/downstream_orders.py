from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.models import User
from app.services.downstream_orders import (
    approve_review,
    create_review_from_callback,
    get_review_attachment_debug,
    get_review_context_messages,
    get_review_detail,
    list_reviews,
    manual_order,
    parse_review_content,
    replace_old_order,
    retry_review_attachment_download,
    void_review,
)

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


class ReviewAttachmentRetryPayload(BaseModel):
    reparse: Optional[bool] = True
    force_download: Optional[bool] = False


def json_response(code=200, message="success", data=None):
    result = {"code": code, "message": message}
    if data is not None:
        result["data"] = data
    return result


@router.get("/reviews", summary="获取待审核订单列表")
async def get_reviews(
    page: int = Query(1, ge=1),
    pageSize: int = Query(20, ge=1, le=100),
    review_status: Optional[str] = Query(None),
    customer_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    data = list_reviews(db, page=page, page_size=pageSize, review_status=review_status or "", customer_id=customer_id)
    return json_response(data=data)


@router.get("/reviews/{review_id}", summary="获取待审核订单详情")
async def get_review(
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
async def get_review_context_messages_api(
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
async def get_review_attachment_debug_api(
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
async def void_review_api(
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
