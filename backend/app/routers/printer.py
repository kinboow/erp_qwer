"""
打印机管理 API — 配置 + 打印队列 + 客户端心跳
客户端接口（/queue/*）无需登录认证，管理接口需要登录。
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

router = APIRouter(prefix="/api/printer", tags=["打印机管理"])


def json_response(code=200, message="success", data=None):
    resp = {"code": code, "message": message}
    if data is not None:
        resp["data"] = data
    return resp


# ---- 配置（需要登录） ----

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
    printer_target_client: str = ""
    printer_target_printer: str = ""
    printer_unshipped_schedule_enabled: str = "false"
    printer_unshipped_schedule_time: str = "09:00"


@router.put("/config", summary="保存打印机配置")
def api_save_config(
    payload: PrinterConfigPayload,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    from app.services.printer_service import save_printer_config
    cfg = save_printer_config(db, payload.model_dump(exclude_unset=True))
    return json_response(data=cfg, message="打印机配置已保存")


# ---- 客户端心跳（无需登录） ----

class HeartbeatPayload(BaseModel):
    hostname: str = ""
    printer_name: str = ""
    printers: list[str] = []


@router.post("/queue/heartbeat", summary="客户端上报心跳")
def api_heartbeat(payload: HeartbeatPayload) -> dict[str, Any]:
    from app.services.printer_service import update_client_heartbeat
    update_client_heartbeat(payload.hostname, payload.printer_name, payload.printers)
    return json_response(message="ok")


@router.get("/client-status", summary="查询打印客户端在线状态（需登录）")
def api_client_status(
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    from app.services.printer_service import get_client_status
    return json_response(data=get_client_status())


@router.get("/clients", summary="查询所有打印客户端状态（需登录）")
def api_clients(
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    from app.services.printer_service import list_client_statuses
    return json_response(data=list_client_statuses())


class TestPrintPayload(BaseModel):
    target_client: str = ""
    target_printer: str = ""


@router.post("/test-print", summary="发送测试打印任务（需登录）")
def api_test_print(
    payload: TestPrintPayload,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    from app.services.printer_service import enqueue_test_print_job
    result = enqueue_test_print_job(db, payload.target_client, payload.target_printer)
    return json_response(data=result, message="测试打印任务已发送")


@router.post("/schedule/test-run", summary="立即测试执行一次昨日未发货定时打印")
def api_schedule_test_run(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    from app.services.printer_service import trigger_unshipped_schedule_run
    try:
        result = trigger_unshipped_schedule_run(trigger_type="manual_test", mark_run_date=False)
        return json_response(data=result, message="定时任务测试执行完成")
    except ValueError as exc:
        return json_response(code=400, message=str(exc))
    except Exception as exc:
        return json_response(code=500, message=f"定时任务测试执行失败: {exc}")


@router.get("/schedule/logs", summary="查询定时任务日志")
def api_schedule_logs(
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    from app.services.printer_service import list_scheduled_task_logs
    return json_response(data=list_scheduled_task_logs(db, task_key="", limit=limit))


# ---- 打印队列 — 客户端接口（无需登录） ----

@router.get("/queue/poll", summary="客户端轮询待打印任务")
def api_poll_queue(
    db: Session = Depends(get_db),
    hostname: str = Query(default="", description="客户端主机名，用于心跳"),
    printer_name: str = Query(default="", description="客户端打印机名"),
    limit: int = Query(default=10, le=50),
) -> dict[str, Any]:
    from app.services.printer_service import poll_print_jobs, update_client_heartbeat
    if hostname:
        update_client_heartbeat(hostname, printer_name)
    jobs = poll_print_jobs(db, hostname=hostname, limit=limit)
    return json_response(data=jobs)


class AckPayload(BaseModel):
    job_id: int
    success: bool
    error: str = ""


@router.post("/queue/ack", summary="客户端回报打印结果")
def api_ack_job(
    payload: AckPayload,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    from app.services.printer_service import ack_print_job
    ack_print_job(db, payload.job_id, payload.success, payload.error)
    return json_response(message="已更新")


@router.get("/queue/download/{object_path:path}", summary="客户端下载待打印 PDF")
def api_download_pdf(
    object_path: str,
    db: Session = Depends(get_db),
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


# ---- 手动入队（需要登录） ----

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
