from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routers import auth, users, wechat, roles, customers, logs, wechat_runtime, wechat_config, downstream_orders

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
