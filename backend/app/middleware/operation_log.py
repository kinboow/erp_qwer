"""
操作日志中间件 —— 自动记录用户的增删改等写操作。

规则:
- 仅记录 POST / PUT / DELETE / PATCH 方法（以及登录接口）
- 跳过纯查询/代理/心跳等路径
- 从 JWT 提取当前用户信息
- 写入 operation_logs 表
"""

import json
import logging
import time
from typing import Optional

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from sqlalchemy import text

from app.database import SessionLocal
from app.utils.security import decode_access_token

logger = logging.getLogger("operation_log")

# ---------- 路径 → 模块 / 操作 / 描述 映射 ----------

# 需要跳过的路径前缀（不记录日志）
SKIP_PREFIXES = (
    "/api/logs",
    "/api/wechat/callback",
    "/api/wechat/proxy/health",
    "/api/wechat/proxy/overview",
    "/api/wechat/proxy/rooms",
    "/api/wechat/proxy/room-members",
    "/api/wechat/proxy/login_window_screenshot",
    "/api/wechat/proxy/wait_login",
    "/api/wechat/proxy/refresh_qrcode",
    "/api/wechat/proxy/kill_process",
    "/api/dashboard",
    "/ws",
    "/sync",
    "/docs",
    "/openapi.json",
    "/favicon",
)

# 路径 → (module, action, description_template)
# description_template 中可使用 {body} 占位符
ROUTE_MAP: dict[str, tuple[str, str, str]] = {
    # 认证
    "POST /api/auth/login":       ("auth",     "login",  "用户登录"),
    "POST /api/auth/logout":      ("auth",     "logout", "用户登出"),

    # 用户管理
    "POST /api/users":            ("user",     "create", "创建用户"),
    "PUT /api/users":             ("user",     "update", "更新用户"),
    "DELETE /api/users":          ("user",     "delete", "删除用户"),

    # 角色管理
    "POST /api/roles":            ("role",     "create", "创建角色"),
    "PUT /api/roles":             ("role",     "update", "更新角色"),
    "DELETE /api/roles":          ("role",     "delete", "删除角色"),

    # 下游客户
    "POST /api/customers":        ("customer", "create", "创建客户"),
    "PUT /api/customers":         ("customer", "update", "更新客户"),
    "DELETE /api/customers":      ("customer", "delete", "删除客户"),
    "POST /api/customers/sync-erp": ("customer", "sync", "同步ERP客户"),

    # 企微配置
    "PUT /api/wechat/config":     ("wechat",   "update", "保存企微配置"),
    "POST /api/wechat/proxy/start": ("wechat", "create", "启动企微实例"),

    # 企微群聊管理
    "POST /api/wechat/rooms/set-internal":   ("wechat", "update", "设置内部群"),
    "POST /api/wechat/rooms/unset-internal": ("wechat", "update", "取消内部群"),

    # 企微实例
    "POST /api/wechat/instances":  ("wechat",  "create", "创建企微实例"),
    "PUT /api/wechat/instances":   ("wechat",  "update", "更新企微实例"),
    "DELETE /api/wechat/instances": ("wechat", "delete", "删除企微实例"),

    # ERP 同步
    "PUT /api/erp/sync/config":          ("erp_sync", "update", "保存ERP同步配置"),
    "POST /api/erp/sync/test-connection": ("erp_sync", "view",  "测试ERP连接"),
    "POST /api/erp/sync/trigger":        ("erp_sync", "sync",  "手动触发全量同步"),
    "POST /api/erp/sync/trigger-orders":    ("erp_sync", "sync", "手动触发订单同步"),
    "POST /api/erp/sync/trigger-shipments": ("erp_sync", "sync", "手动触发发货单同步"),
    "POST /api/erp/sync/trigger-products":  ("erp_sync", "sync", "手动触发产品同步"),
    "POST /api/erp/sync/trigger-inventory": ("erp_sync", "sync", "手动触发库存同步"),
    "POST /api/erp/sync/upload-qr":      ("erp_sync", "update", "上传账套二维码"),

    # AI 配置
    "PUT /api/ai/config":         ("ai",      "update", "保存AI配置"),
    "POST /api/ai/test":          ("ai",      "view",   "测试AI连接"),

    # 订单审核
    "POST /api/downstream-orders/reviews": ("order_review", "update", "审核订单"),
    "PUT /api/downstream-orders/reviews":  ("order_review", "update", "更新审核"),
}


def _match_route(method: str, path: str) -> Optional[tuple[str, str, str]]:
    """尝试匹配路径，支持路径参数 (如 /api/users/123)"""
    key = f"{method} {path}"
    if key in ROUTE_MAP:
        return ROUTE_MAP[key]
    # 尝试截断路径参数匹配，例如 PUT /api/users/5 → PUT /api/users
    parts = path.rstrip("/").rsplit("/", 1)
    if len(parts) == 2:
        parent = parts[0]
        parent_key = f"{method} {parent}"
        if parent_key in ROUTE_MAP:
            return ROUTE_MAP[parent_key]
    return None


def _extract_user_from_token(request: Request) -> tuple[Optional[int], Optional[str]]:
    """从 Authorization header 中提取 user_id 和 username"""
    auth = request.headers.get("authorization") or ""
    if not auth.lower().startswith("bearer "):
        return None, None
    token = auth[7:].strip()
    if not token:
        return None, None
    payload = decode_access_token(token)
    if not payload:
        return None, None
    uid = payload.get("user_id") or payload.get("userId")
    uname = payload.get("username") or ""
    return uid, uname


def _safe_body_summary(body: bytes, max_len: int = 500) -> str:
    """安全地将请求体截断为摘要文本"""
    if not body:
        return ""
    try:
        text_body = body.decode("utf-8", errors="ignore")
        obj = json.loads(text_body)
        # 脱敏：去掉密码字段
        for k in ("password", "api_key", "apiKey", "api_secret"):
            if k in obj:
                obj[k] = "***"
        summary = json.dumps(obj, ensure_ascii=False, default=str)
    except Exception:
        summary = body.decode("utf-8", errors="ignore")
    return summary[:max_len] if len(summary) > max_len else summary


class OperationLogMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        method = request.method.upper()
        path = request.url.path

        # 仅对写操作（+ 登录）记录
        if method not in ("POST", "PUT", "DELETE", "PATCH"):
            return await call_next(request)

        # 跳过不需要记录的路径
        for prefix in SKIP_PREFIXES:
            if path.startswith(prefix):
                return await call_next(request)

        # 匹配路由
        route_info = _match_route(method, path)
        if not route_info:
            return await call_next(request)

        module, action, desc_template = route_info

        # 提取用户（登录接口此时还没 token，从请求体取 username）
        user_id, username = _extract_user_from_token(request)

        # 读取请求体
        body = b""
        try:
            body = await request.body()
        except Exception:
            pass

        # 登录接口从 body 取 username
        if path == "/api/auth/login" and not username:
            try:
                obj = json.loads(body)
                username = obj.get("username", "")
            except Exception:
                pass

        body_summary = _safe_body_summary(body)

        # 执行请求
        start = time.time()
        response = await call_next(request)
        duration_ms = int((time.time() - start) * 1000)

        # 判断成功/失败
        status_ok = 1 if 200 <= response.status_code < 400 else 0
        ip = request.client.host if request.client else ""

        # 构建描述
        description = desc_template
        # 如果有路径参数，把 ID 附到描述后面
        parts = path.rstrip("/").rsplit("/", 1)
        if len(parts) == 2 and parts[1].isdigit():
            description = f"{desc_template} (ID:{parts[1]})"

        # 异步写入 DB
        try:
            db = SessionLocal()
            try:
                db.execute(text(
                    "INSERT INTO operation_logs "
                    "(user_id, username, module, action, method, path, ip, user_agent, "
                    " request_data, status, duration, created_at) "
                    "VALUES (:user_id, :username, :module, :action, :method, :path, :ip, :ua, "
                    " :req_data, :status, :duration, NOW())"
                ), {
                    "user_id": user_id,
                    "username": username or "",
                    "module": module,
                    "action": action,
                    "method": method,
                    "path": path,
                    "ip": ip,
                    "ua": (request.headers.get("user-agent") or "")[:500],
                    "req_data": body_summary,
                    "status": status_ok,
                    "duration": duration_ms,
                })
                db.commit()
            except Exception as e:
                logger.warning("写入操作日志失败: %s", e)
                try:
                    db.rollback()
                except Exception:
                    pass
            finally:
                db.close()
        except Exception as e:
            logger.warning("获取 DB 连接失败: %s", e)

        return response
