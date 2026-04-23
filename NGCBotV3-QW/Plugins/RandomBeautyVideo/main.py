import aiohttp
import os
from loguru import logger
from Core.EventDispatcher import messageHandle
from Core.EVentType import EventType
from NGCBotApi import NGCBotApi

bot = NGCBotApi()
pluginConfig = {}
DOWNLOAD_DIR = os.path.join(os.path.dirname(__file__), 'videos')

async def onLoad():
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    logger.info(f"[{pluginConfig.get('name', 'RandomBeautyVideo')}] 插件已加载")
    logger.info(f"触发词: {pluginConfig.get('settings', {}).get('keywords', [])}")

async def onUnload():
    logger.info(f"[{pluginConfig.get('name', 'RandomBeautyVideo')}] 插件已卸载")

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

    # 获取并下载美女视频
    local_path = await download_beauty_video(settings.get('apiUrl', ''))

    if local_path:
        await bot.sendVideo(robotId, reply_target, local_path)
    else:
        await bot.sendText(robotId, reply_target, "获取视频失败，请稍后再试~")

async def download_beauty_video(api_url: str) -> str:
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(api_url, timeout=aiohttp.ClientTimeout(total=30)) as response:
                if response.status == 200:
                    import time
                    filename = f"beauty_{int(time.time())}.mp4"
                    local_path = os.path.join(DOWNLOAD_DIR, filename)

                    with open(local_path, 'wb') as f:
                        f.write(await response.read())

                    return local_path
                logger.error(f"API返回错误: {response.status}")
                return None
    except Exception as e:
        logger.error(f"下载美女视频失败: {e}")
        return None
