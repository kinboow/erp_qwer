import logging

from fastapi import FastAPI, Request
from fastapi import Body, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.routers import auth, users, wechat, roles, customers, logs, wechat_runtime, wechat_config, downstream_orders
from app.services.wechat_runtime_compat import ingest_runtime_message
from app.services.wechat_ws_service import wechat_ws_service

logger = logging.getLogger(__name__)

# 创建FastAPI应用实例
app = FastAPI(
    title="工厂智能化管理系统API",
    description="基于FastAPI的工厂管理系统后端接口",
    version="1.0.0",
    docs_url="/docs",  # Swagger文档地址
    redoc_url="/redoc"  # ReDoc文档地址
)

# 配置跨域中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 生产环境应该指定具体域名
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由模块
app.include_router(auth.router, prefix="/api/auth")
app.include_router(users.router, prefix="/api/users")
app.include_router(roles.router, prefix="/api/roles")
app.include_router(customers.router, prefix="/api/customers")
app.include_router(logs.router, prefix="/api/logs")
app.include_router(wechat.router, prefix="/api/wechat", tags=["企业微信管理"])
app.include_router(wechat_runtime.router, prefix="/api/wechat")
app.include_router(wechat_config.router, prefix="/api/wechat")
app.include_router(downstream_orders.router, prefix="/api/downstream-orders")


@app.on_event("startup")
async def restore_wechat_message_receivers():
    await wechat_ws_service.auto_connect_from_saved_config()


@app.api_route("/qwmspush", methods=["GET", "POST"], summary="兼容 NGCBot HTTP 回调", tags=["企业微信运行时"])
async def root_sync_callback(request: Request):
    wxid = request.query_params.get("wxid", "")
    instance_id = request.query_params.get("instanceId", "")
    request_body = {}
    try:
        request_body = await request.json()
    except Exception:
        pass
    db: Session = SessionLocal()
    try:
        result = await ingest_runtime_message(
            db,
            request_body or {},
            source="http_callback",
            instance_id=instance_id or None,
            wxid=wxid or None,
        )
        return {"code": 200, "message": "回调接收成功", "data": result}
    except Exception as exc:
        logger.exception("[/sync] 处理回调异常")
        return {"code": 500, "message": str(exc)}
    finally:
        db.close()


@app.websocket("/ws")
async def root_ws_callback(websocket: WebSocket):
    await websocket.accept()
    wxid = (websocket.query_params.get("wxid") or "").strip()
    instance_id = (websocket.query_params.get("instanceId") or "").strip()
    db: Session = SessionLocal()
    try:
        while True:
            message = await websocket.receive()
            payload = None
            if message.get("text") is not None:
                payload = message.get("text")
            elif message.get("bytes") is not None:
                try:
                    payload = message.get("bytes", b"").decode("utf-8")
                except Exception:
                    payload = {"raw_bytes": message.get("bytes", b"").hex()}
            if payload is None:
                continue
            await ingest_runtime_message(
                db,
                payload,
                source="websocket",
                instance_id=instance_id or None,
                wxid=wxid or None,
            )
            await websocket.send_json({"code": 200, "message": "received"})
    except WebSocketDisconnect:
        return
    finally:
        db.close()


@app.get("/", summary="根路径", tags=["系统"])
async def root():
    """API根路径，返回系统信息"""
    return {"message": "工厂智能化管理系统API", "version": "1.0.0"}


@app.get("/health", summary="健康检查", tags=["系统"])
async def health_check():
    """健康检查接口，用于监控系统状态"""
    return {"status": "ok", "message": "系统运行正常"}


if __name__ == "__main__":
    import uvicorn
    from app.config import settings

    # 启动服务器
    uvicorn.run(
        "main:app",
        host=settings.API_HOST,
        port=settings.API_PORT,
        reload=settings.DEBUG
    )
