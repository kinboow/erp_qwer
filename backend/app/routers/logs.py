from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import Optional
from pathlib import Path
import json

from app.database import get_db
from app.models import OperationLog, User
from app.dependencies import get_current_user
from app.services.message_logs import list_message_logs

router = APIRouter(tags=["日志管理"])


def json_response(code=200, message="success", data=None):
    resp = {"code": code, "message": message}
    if data is not None:
        resp["data"] = data
    return resp


@router.get("/system", summary="获取系统日志")
async def get_system_logs(
    page: int = Query(1, ge=1),
    pageSize: int = Query(20, ge=1, le=100),
    level: Optional[str] = Query(None),
    keyword: Optional[str] = Query(None),
    startDate: Optional[str] = Query(None),
    endDate: Optional[str] = Query(None),
    current_user: User = Depends(get_current_user)
):
    log_file = Path(__file__).resolve().parents[3] / "logs" / "combined.log"
    if not log_file.exists():
        return json_response(data={"list": [], "total": 0})

    entries = []
    for line in log_file.read_text(encoding="utf-8", errors="ignore").splitlines():
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except Exception:
            continue
        log_entry = {
            "timestamp": item.get("timestamp", ""),
            "level": item.get("level", "info"),
            "service": item.get("service", ""),
            "message": item.get("message", ""),
        }
        if level and log_entry["level"] != level:
            continue
        if keyword and keyword.lower() not in log_entry["message"].lower():
            continue
        if startDate and log_entry["timestamp"] < startDate:
            continue
        if endDate and log_entry["timestamp"] > f"{endDate}T23:59:59":
            continue
        entries.append(log_entry)

    entries.reverse()
    total = len(entries)
    start = (page - 1) * pageSize
    return json_response(data={"list": entries[start:start + pageSize], "total": total})


@router.get("/operation", summary="获取操作日志")
async def get_operation_logs(
    page: int = Query(1, ge=1),
    pageSize: int = Query(20, ge=1, le=100),
    module: Optional[str] = Query(None),
    action: Optional[str] = Query(None),
    keyword: Optional[str] = Query(None),
    startDate: Optional[str] = Query(None),
    endDate: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    conditions = []
    params = {}
    if module:
        conditions.append("module = :module")
        params["module"] = module
    if action:
        conditions.append("action = :action")
        params["action"] = action
    if keyword:
        conditions.append("(username LIKE :keyword OR request_data LIKE :keyword OR response_data LIKE :keyword OR error_msg LIKE :keyword OR path LIKE :keyword)")
        params["keyword"] = f"%{keyword}%"
    if startDate:
        conditions.append("created_at >= :startDate")
        params["startDate"] = f"{startDate} 00:00:00"
    if endDate:
        conditions.append("created_at <= :endDate")
        params["endDate"] = f"{endDate} 23:59:59"

    where_sql = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    total = db.execute(text(f"SELECT COUNT(*) AS total FROM operation_logs {where_sql}"), params).mappings().first()["total"]

    query = text(f"SELECT id, username, module, action, ip, created_at, path, request_data, response_data, error_msg, status FROM operation_logs {where_sql} ORDER BY created_at DESC LIMIT :limit OFFSET :offset")
    rows = db.execute(query, {**params, "limit": pageSize, "offset": (page - 1) * pageSize}).mappings().all()
    result = []
    for row in rows:
        item = dict(row)
        item["description"] = item.get("path") or item.get("error_msg") or item.get("request_data") or "-"
        result.append(item)
    return json_response(data={"list": result, "total": total})


@router.get("/messages", summary="获取消息日志")
async def get_message_logs(
    page: int = Query(1, ge=1),
    pageSize: int = Query(20, ge=1, le=100),
    source: Optional[str] = Query(None),
    message_type: Optional[str] = Query(None),
    keyword: Optional[str] = Query(None),
    startDate: Optional[str] = Query(None),
    endDate: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    data = list_message_logs(
        db,
        page=page,
        page_size=pageSize,
        source=source or "",
        message_type=message_type or "",
        keyword=keyword or "",
        start_date=startDate,
        end_date=endDate,
    )
    return json_response(data=data)
