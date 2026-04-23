import aiohttp
from loguru import logger
from Core.EventDispatcher import messageHandle
from Core.EVentType import EventType
from NGCBotApi import NGCBotApi

bot = NGCBotApi()
pluginConfig = {}

async def onLoad():
    logger.info(f"[{pluginConfig.get('name', 'KFC')}] 插件已加载")
    logger.info(f"触发词: {pluginConfig.get('settings', {}).get('keywords', [])}")

async def onUnload():
    logger.info(f"[{pluginConfig.get('name', 'KFC')}] 插件已卸载")

@messageHandle(type=EventType.TEXT_MESSAGE)
async def handle_text_message(data: dict):
    settings = pluginConfig.get('settings', {})
    message_data = data.get('message', {}).get('data')

    msg_content = message_data.get('content', '').strip()
    robotId = data.get('wxid', '')
    sender = message_data.get('sender', '')

    if robotId == sender:
        return

    conversation_id = message_data.get('conversation_id', '')
    is_group = conversation_id.startswith('R:')

    if is_group:
        enabled_groups = settings.get('enabledGroups', [])
        if not enabled_groups or conversation_id not in enabled_groups:
            return
        reply_target = conversation_id
    else:
        if not settings.get('enablePrivateChat', True):
            return
        reply_target = conversation_id

    # 检查是否包含触发词
    keywords = settings.get('keywords', [])
    if not any(keyword == msg_content for keyword in keywords):
        return

    # 获取KFC文案
    kfc_text = await get_kfc_text(settings.get('apiUrl', ''))

    if kfc_text:
        if is_group:
            await bot.sendAtText(robotId, reply_target, ' ' + kfc_text, [sender])
        else:
            await bot.sendText(robotId, reply_target, kfc_text)
    else:
        await bot.sendText(robotId, reply_target, "获取KFC文案失败，请稍后再试~")

async def get_kfc_text(api_url: str) -> str:
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(api_url, timeout=aiohttp.ClientTimeout(total=10)) as response:
                if response.status == 200:
                    result = await response.json()
                    if result.get('code') == 200:
                        return result.get('data', '').replace('\\n', '\n')
                logger.error(f"API返回错误: {response.status}")
                return None
    except Exception as e:
        logger.error(f"获取KFC文案失败: {e}")
        return None
