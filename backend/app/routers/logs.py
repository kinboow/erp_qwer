from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import Optional
import json

from app.database import get_db
from app.models import OperationLog, User
from app.dependencies import get_current_user
from app.services.message_logs import list_message_logs

router = APIRouter(tags=["日志管理"])


def _fmt_row(row) -> dict:
    """将查询行中的 datetime 字段统一格式化为 YYYY-MM-DD HH:MM:SS"""
    item = dict(row)
    for k, v in item.items():
        if isinstance(v, datetime):
            item[k] = v.strftime("%Y-%m-%d %H:%M:%S")
    return item


def json_response(code=200, message="success", data=None):
    resp = {"code": code, "message": message}
    if data is not None:
        resp["data"] = data
    return resp


@router.get("/system", summary="获取系统日志")
def get_system_logs(
    page: int = Query(1, ge=1),
    pageSize: int = Query(20, ge=1, le=100),
    level: Optional[str] = Query(None),
    keyword: Optional[str] = Query(None),
    startDate: Optional[str] = Query(None),
    endDate: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    from app.services.db_log_handler import ensure_system_logs_table
    ensure_system_logs_table(db)

    conditions = []
    params = {}
    if level:
        conditions.append("level = :level")
        params["level"] = level
    if keyword:
        conditions.append("(message LIKE :keyword OR service LIKE :keyword)")
        params["keyword"] = f"%{keyword}%"
    if startDate:
        conditions.append("timestamp >= :startDate")
        params["startDate"] = f"{startDate} 00:00:00"
    if endDate:
        conditions.append("timestamp <= :endDate")
        params["endDate"] = f"{endDate} 23:59:59"

    where_sql = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    total = db.execute(text(f"SELECT COUNT(*) AS total FROM system_logs {where_sql}"), params).mappings().first()["total"]

    query = text(f"SELECT id, timestamp, level, service, message FROM system_logs {where_sql} ORDER BY timestamp DESC LIMIT :limit OFFSET :offset")
    rows = db.execute(query, {**params, "limit": pageSize, "offset": (page - 1) * pageSize}).mappings().all()
    result = [_fmt_row(row) for row in rows]
    return json_response(data={"list": result, "total": total})


@router.get("/operation", summary="获取操作日志")
def get_operation_logs(
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

    query = text(f"SELECT id, username, module, action, ip, created_at, path, request_data, response_data, error_msg, status, duration FROM operation_logs {where_sql} ORDER BY created_at DESC LIMIT :limit OFFSET :offset")
    rows = db.execute(query, {**params, "limit": pageSize, "offset": (page - 1) * pageSize}).mappings().all()
    # 路径 → 可读描述映射
    PATH_DESC = {
        "/api/auth/login": "用户登录",
        "/api/auth/logout": "用户登出",
        "/api/users": "用户管理",
        "/api/roles": "角色管理",
        "/api/customers": "客户管理",
        "/api/customers/sync-erp": "同步ERP客户",
        "/api/wechat/config": "企微配置",
        "/api/wechat/proxy/start": "启动企微实例",
        "/api/wechat/rooms/set-internal": "设置内部群",
        "/api/wechat/rooms/unset-internal": "取消内部群",
        "/api/wechat/instances": "企微实例",
        "/api/erp/sync/config": "ERP同步配置",
        "/api/erp/sync/test-connection": "测试ERP连接",
        "/api/erp/sync/trigger": "手动全量同步",
        "/api/erp/sync/trigger-orders": "手动订单同步",
        "/api/erp/sync/trigger-shipments": "手动发货单同步",
        "/api/erp/sync/trigger-products": "手动产品同步",
        "/api/erp/sync/trigger-inventory": "手动库存同步",
        "/api/erp/sync/trigger-unshipped": "手动未发货报表同步",
        "/api/erp/sync/trigger-customers": "手动客户同步",
        "/api/erp/sync/upload-qr": "上传账套二维码",
        "/api/ai/config": "AI配置",
        "/api/ai/test": "测试AI连接",
        "/api/downstream-orders/reviews": "订单审核",
    }

    result = []
    for row in rows:
        item = _fmt_row(row)
        path_val = item.get("path") or ""
        # 尝试匹配完整路径，然后截断数字尾部
        desc = PATH_DESC.get(path_val)
        if not desc:
            parts = path_val.rstrip("/").rsplit("/", 1)
            if len(parts) == 2 and parts[1].isdigit():
                desc = PATH_DESC.get(parts[0])
                if desc:
                    desc = f"{desc} (ID:{parts[1]})"
        if not desc:
            desc = path_val
        # 附加请求摘要
        req_data = item.get("request_data") or ""
        if req_data and len(req_data) < 200:
            try:
                obj = json.loads(req_data)
                # 提取有意义的字段
                hints = []
                for k in ("username", "real_name", "name", "customer_name", "room_name", "room_id", "code"):
                    if k in obj and obj[k]:
                        hints.append(str(obj[k]))
                if hints:
                    desc = f"{desc}: {', '.join(hints[:3])}"
            except Exception:
                pass
        item["description"] = desc
        result.append(item)
    return json_response(data={"list": result, "total": total})


@router.get("/messages", summary="获取消息日志")
def get_message_logs(
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
