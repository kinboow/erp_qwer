"""发货单扫码识别结果列表 API"""
import asyncio
import json
import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.dependencies import get_current_user, get_db
from app.models import User
from app.services.downstream_support import ensure_downstream_support_tables
from app.services.shipping_scan_handler import approve_shipping_scan_record, void_shipping_scan_record

logger = logging.getLogger(__name__)

router = APIRouter(tags=["发货扫码记录"])


def json_response(code=200, message="success", data=None):
    resp = {"code": code, "message": message}
    if data is not None:
        resp["data"] = data
    return resp


class ShippingScanReviewPayload(BaseModel):
    review_note: Optional[str] = ""


@router.get("/scan-records", summary="获取发货扫码识别记录列表")
def list_scan_records(
    page: int = Query(1, ge=1),
    pageSize: int = Query(20, ge=1, le=100),
    scan_status: Optional[str] = Query(None),
    order_no: Optional[str] = Query(None),
    room_id: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ensure_downstream_support_tables(db)
    where_parts = ["1=1"]
    params: dict[str, Any] = {}

    if scan_status:
        where_parts.append("s.scan_status = :scan_status")
        params["scan_status"] = scan_status
    if order_no:
        where_parts.append("s.order_no LIKE :order_no")
        params["order_no"] = f"%{order_no}%"
    if room_id:
        where_parts.append("s.room_id = :room_id")
        params["room_id"] = room_id

    where_sql = " AND ".join(where_parts)

    # 总数
    total = db.execute(
        text(f"SELECT COUNT(*) FROM shipping_scan_records s WHERE {where_sql}"),
        params,
    ).scalar() or 0

    # 分页
    offset = (page - 1) * pageSize
    rows = db.execute(
        text(
            f"SELECT s.id, s.order_no, s.paper_id, s.qr_content, s.code_source, "
            f"s.room_id, s.room_name, s.instance_id, s.sender_id, s.msg_log_id, "
            f"s.scan_status, s.ai_parsed_json, s.shipment_no, s.shipment_result, "
            f"s.notification_sent, s.error_message, s.review_note, s.reviewed_by, s.reviewed_at, s.fallback_ocr_json, s.created_at, s.updated_at, "
            f"m.oss_key AS image_oss_key, m.sender_name AS scanner_name "
            f"FROM shipping_scan_records s "
            f"LEFT JOIN message_logs m ON s.msg_log_id = m.id "
            f"WHERE {where_sql} "
            f"ORDER BY s.created_at DESC "
            f"LIMIT :limit OFFSET :offset"
        ),
        {**params, "limit": pageSize, "offset": offset},
    ).mappings().all()

    result = []
    for r in rows:
        item = dict(r)
        # 解析 AI 识别结果
        ai_parsed = None
        try:
            ai_parsed = json.loads(item.get("ai_parsed_json") or "null")
        except Exception:
            pass
        item["ai_parsed"] = ai_parsed
        item.pop("ai_parsed_json", None)

        # 解析发货结果
        shipment_result = None
        try:
            shipment_result = json.loads(item.get("shipment_result") or "null")
        except Exception:
            pass
        item["shipment_result_detail"] = shipment_result
        item.pop("shipment_result", None)

        fallback_ocr = None
        try:
            fallback_ocr = json.loads(item.get("fallback_ocr_json") or "null")
        except Exception:
            pass
        item["fallback_ocr"] = fallback_ocr
        item.pop("fallback_ocr_json", None)

        # 时间格式化
        for k in ("created_at", "updated_at", "reviewed_at"):
            if item.get(k):
                item[k] = str(item[k])

        result.append(item)

    return json_response(data={
        "list": result,
        "total": total,
        "page": page,
        "pageSize": pageSize,
    })


@router.get("/scan-records/stats", summary="发货扫码统计")
def scan_records_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ensure_downstream_support_tables(db)
    row = db.execute(text(
        "SELECT "
        "COUNT(*) AS total, "
        "SUM(scan_status = 'success') AS success_count, "
        "SUM(scan_status = 'failed') AS failed_count, "
        "SUM(scan_status IN ('pending', 'parsing')) AS pending_count, "
        "SUM(scan_status = 'review_pending') AS review_pending_count, "
        "SUM(scan_status = 'voided') AS voided_count "
        "FROM shipping_scan_records"
    )).mappings().first()
    return json_response(data=dict(row) if row else {})


@router.post("/scan-records/{record_id}/approve", summary="审核通过发货识别记录并下发货单")
async def approve_scan_record_api(
    record_id: int,
    payload: ShippingScanReviewPayload,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ensure_downstream_support_tables(db)
    try:
        data = await approve_shipping_scan_record(db, record_id, current_user, payload.review_note or "")
        return json_response(message="审核下发货单成功", data=data)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/scan-records/{record_id}/void", summary="作废发货识别记录")
def void_scan_record_api(
    record_id: int,
    payload: ShippingScanReviewPayload,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ensure_downstream_support_tables(db)
    try:
        data = void_shipping_scan_record(db, record_id, current_user, payload.review_note or "")
        return json_response(message="已作废发货识别记录", data=data)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/scan-records/stream", summary="SSE 实时推送发货扫码记录变动")
async def scan_records_stream(request: Request):
    """Server-Sent Events 端点，发货扫码记录变动时实时推送通知"""
    from app.services.shipping_scan_events import subscribe

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
