# -*- coding: utf-8 -*-

import json
from loguru import logger
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from Core.PluginManager import pluginManager
from Config.ConfigServer import getCallbackConfig
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 启动时加载所有插件
    logger.info("=" * 60)
    logger.info("NGCBot V3 启动中...")
    logger.info("=" * 60)
    await pluginManager.loadAllPlugins()
    logger.success("NGCBot V3 启动完成！")
    logger.info("=" * 60)

    yield

    # 关闭时卸载所有插件
    logger.info("NGCBot V3 正在关闭...")
    await pluginManager.unloadAllPlugins()
    logger.info("NGCBot V3 已关闭")

# 创建FastAPI应用
app = FastAPI(title="NGCBot V3", version="3.0.0", lifespan=lifespan)

@app.post("/sync")
async def receiveCallback(request: Request):
    """接收微信回调数据"""
    try:
        body = await request.body()
        data = json.loads(body.decode('utf-8'))

        # 提取事件类型：message.type 和 message.data.content_type
        message = data.get('message', {})
        eventType = message.get('type', 0)
        messageData = message.get('data', {})
        contentType = messageData.get('content_type', 0)  # contentType可能是数字或字符串

        # 记录日志
        logger.info(f"收到回调: type={eventType}, contentType={contentType}")
        logger.debug(f"回调数据: {json.dumps(data, ensure_ascii=False)}")

        # 分发事件到插件
        await pluginManager.dispatchEvent(eventType, contentType, data)

        return JSONResponse(status_code=200, content={"status": "success"})

    except Exception as e:
        logger.error(f"处理回调数据失败: {e}", exc_info=True)
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})


if __name__ == "__main__":
    import uvicorn

    # 从配置文件读取回调服务器配置
    callbackConfig = getCallbackConfig()
    HOST = callbackConfig.get('HOST', '127.0.0.1')
    PORT = callbackConfig.get('PORT', 5006)

    logger.info(f"NGCBot V3 启动配置:")
    logger.info(f"监听地址: http://{HOST}:{PORT}")
    logger.info(f"回调端点: http://{HOST}:{PORT}/sync")

    uvicorn.run(
        "main:app",
        host=HOST,
        port=PORT,
        reload=False,
        log_level="info"
    )

