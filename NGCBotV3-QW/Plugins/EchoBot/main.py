# -*- coding: utf-8 -*-

from loguru import logger
from NGCBotApi import NGCBotApi
from Core.EventDispatcher import messageHandle
from Core.EVentType import EventType

# 初始化Bot API
bot = NGCBotApi()

# 插件配置（由插件管理器注入）
pluginConfig = {}


@messageHandle(type=EventType.TEXT_MESSAGE)
async def onTextMessage(data: dict):
    """处理文本消息通知 - 回声功能 (11041)"""
    try:
        message = data.get('message', {})
        messageData = message.get('data', {})
        content = messageData.get('content', '')
        conversationId = messageData.get('conversation_id', '')
        sender = messageData.get('sender', '')
        robotId = data.get('wxid', '')


        if not content or not content.strip():
            return

        # 读取插件配置
        settings = pluginConfig.get('settings', {})
        replyPrefix = settings.get('replyPrefix', '[EchoBot] ')
        onlyInGroup = settings.get('onlyInGroup', False)

        # 判断是否为群聊（conversation_id以R:开头表示群聊）
        isGroup = conversationId.startswith('R:')
        
        # 如果设置了只在群聊中工作
        if onlyInGroup and not isGroup:
            return

        # 构造回复消息
        replyMsg = f"{replyPrefix}{content}"

        # 确定回复目标
        if conversationId == robotId:
            return

        if robotId == sender:
            return
            
        logger.info(f"EchoBot收到: {content}, 将回复到: {conversationId}")
        logger.debug(f"EchoBot准备发送 - robotId={robotId}, receive={conversationId}, content={replyMsg}")
        
        # 发送回复
        result = await bot.sendText(robotId=robotId, receive=conversationId, content=replyMsg)
        logger.info(f"EchoBot发送结果: {result}")

    except Exception as e:
        logger.error(f"EchoBot处理失败: {e}", exc_info=True)


async def onLoad():
    """插件加载时调用"""
    logger.success("EchoBot插件已加载")


async def onUnload():
    """插件卸载时调用"""
    logger.info("EchoBot插件已卸载")

