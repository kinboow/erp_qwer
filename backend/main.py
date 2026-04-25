import logging

import httpx
from fastapi import FastAPI, Request
from fastapi import Body, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.routers import auth, users, wechat, roles, customers, logs, wechat_runtime, wechat_config, downstream_orders, erp_sync, sales_orders, sales_shipments, products, dashboard
from app.services.wechat_runtime_compat import ingest_runtime_message
from app.services.wechat_ws_service import wechat_ws_service
from app.services.erp_health import start_erp_health_checker, stop_erp_health_checker
from app.services.wechat_health import start_wechat_health_checker, stop_wechat_health_checker

# ncloud2 ERP API 子模块
from app.ncloud.client.erp_client import ERPClient
from app.ncloud.exceptions import register_exception_handlers as register_ncloud_exception_handlers
from app.ncloud.routers import auth as ncloud_auth, base as ncloud_base, sales_orders as ncloud_sales_orders
from app.ncloud.routers import shipments as ncloud_shipments, reconciliation as ncloud_reconciliation
from app.ncloud.routers import unshipped_report as ncloud_unshipped_report, inventory as ncloud_inventory

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
app.include_router(erp_sync.router, prefix="/api/erp/sync", tags=["ERP-同步"])
app.include_router(sales_orders.router, prefix="/api/sales-orders", tags=["销售订单"])
app.include_router(sales_shipments.router, prefix="/api/sales-shipments", tags=["销售发货单"])
app.include_router(products.router, prefix="/api/products", tags=["产品列表"])
app.include_router(dashboard.router, prefix="/api/dashboard", tags=["数据看板"])

# ncloud2 ERP API 路由（弘兆云 ERP 操作）
app.include_router(ncloud_auth.router, prefix="/api/erp", tags=["ERP-认证"])
app.include_router(ncloud_base.router, prefix="/api/erp", tags=["ERP-基础数据"])
app.include_router(ncloud_sales_orders.router, prefix="/api/erp", tags=["ERP-销售订单"])
app.include_router(ncloud_shipments.router, prefix="/api/erp", tags=["ERP-销售发货"])
app.include_router(ncloud_reconciliation.router, prefix="/api/erp", tags=["ERP-销售对账"])
app.include_router(ncloud_unshipped_report.router, prefix="/api/erp", tags=["ERP-未发货报表"])
app.include_router(ncloud_inventory.router, prefix="/api/erp", tags=["ERP-库存"])

# 注册 ncloud 异常处理器
register_ncloud_exception_handlers(app)


@app.on_event("startup")
async def startup_event():
    # 从数据库加载 ERP 配置到 ncloud settings（这样无需每次手动点保存）
    try:
        from app.services.erp_sync import _get_db_config
        from app.ncloud.config import settings as ncloud_settings
        cfg = _get_db_config()
        ncloud_settings._override = {
            "NCLOUD_BASE_URL": cfg.get("erp_base_url") or "",
            "NCLOUD_USERNAME": cfg.get("erp_username") or "",
            "NCLOUD_PASSWORD": cfg.get("erp_password") or "",
            "NCLOUD_QR_IMAGE_PATH": cfg.get("erp_qr_image_path") or "",
        }
        logger.info("[Startup] 已从数据库加载 ERP 配置, base_url=%s", cfg.get("erp_base_url"))
    except Exception as e:
        logger.warning("[Startup] 加载数据库 ERP 配置失败（可能表不存在）: %s", e)

    # 初始化 ncloud2 ERP 客户端
    http_client = httpx.AsyncClient(
        headers={
            "User-Agent": "ncloud2api/0.2",
            "Accept": "application/json, text/javascript, */*; q=0.01",
        },
        follow_redirects=False,
        trust_env=False,
    )
    erp_client = ERPClient(http_client)
    app.state.http_client = http_client
    app.state.erp_client = erp_client

    # 恢复企业微信 WebSocket 连接
    await wechat_ws_service.auto_connect_from_saved_config()

    # 启动 ERP 销售订单定时同步
    from app.services.erp_sync import start_sync_scheduler
    start_sync_scheduler(erp_client)

    # 启动 ERP 健康检查轮询（每5分钟）
    start_erp_health_checker(interval_seconds=300)

    # 启动企微健康检查轮询（每5分钟）
    start_wechat_health_checker(interval_seconds=300)


@app.on_event("shutdown")
async def shutdown_event():
    # 停止健康检查轮询
    stop_erp_health_checker()
    stop_wechat_health_checker()

    # 关闭 ERP HTTP 客户端
    http_client = getattr(app.state, "http_client", None)
    if http_client:
        try:
            await http_client.aclose()
        except Exception:
            pass


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
