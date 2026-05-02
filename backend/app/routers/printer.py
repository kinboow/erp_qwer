"""
打印机管理 API — 配置 + 打印队列（供打印客户端轮询）
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User
from app.dependencies import get_current_user
from app.utils.response import json_response

router = APIRouter(prefix="/api/printer", tags=["打印机管理"])


# ---- 配置 ----

@router.get("/config", summary="获取打印机配置")
def api_get_config(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    from app.services.printer_service import get_printer_config
    return json_response(data=get_printer_config(db))


class PrinterConfigPayload(BaseModel):
    printer_name: str = ""
    printer_auto_print: str = "false"


@router.put("/config", summary="保存打印机配置")
def api_save_config(
    payload: PrinterConfigPayload,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    from app.services.printer_service import save_printer_config
    cfg = save_printer_config(db, payload.model_dump())
    return json_response(data=cfg, message="打印机配置已保存")


# ---- 打印队列（供客户端轮询） ----

@router.get("/queue/poll", summary="客户端轮询待打印任务")
def api_poll_queue(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    limit: int = Query(default=10, le=50),
) -> dict[str, Any]:
    from app.services.printer_service import poll_print_jobs
    jobs = poll_print_jobs(db, limit)
    return json_response(data=jobs)


class AckPayload(BaseModel):
    job_id: int
    success: bool
    error: str = ""


@router.post("/queue/ack", summary="客户端回报打印结果")
def api_ack_job(
    payload: AckPayload,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    from app.services.printer_service import ack_print_job
    ack_print_job(db, payload.job_id, payload.success, payload.error)
    return json_response(message="已更新")


@router.get("/queue/download/{object_path:path}", summary="客户端下载待打印 PDF")
def api_download_pdf(
    object_path: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    import io
    from app.utils.oss_client import oss_client
    try:
        pdf_bytes = oss_client.download_file(object_path)
        return StreamingResponse(
            io.BytesIO(pdf_bytes),
            media_type="application/pdf",
            headers={"Content-Disposition": f"attachment; filename={object_path.split('/')[-1]}"},
        )
    except Exception as exc:
        return json_response(code=404, message=f"文件不存在: {exc}")


# ---- 手动入队 ----

class EnqueuePayload(BaseModel):
    order_no: str
    doc_type: str = "picking"


@router.post("/queue/enqueue", summary="手动将订单加入打印队列")
def api_enqueue(
    payload: EnqueuePayload,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    from app.services.printer_service import enqueue_print_job
    try:
        result = enqueue_print_job(db, payload.order_no, payload.doc_type)
        return json_response(data=result, message="已加入打印队列")
    except Exception as exc:
        return json_response(code=500, message=f"入队失败: {exc}")
