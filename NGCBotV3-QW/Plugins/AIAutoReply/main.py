import aiohttp
from loguru import logger
from Core.EventDispatcher import messageHandle
from Core.EVentType import EventType
from NGCBotApi import NGCBotApi

bot = NGCBotApi()
pluginConfig = {}
conversation_history = {}

async def onLoad():
    logger.info(f"[{pluginConfig.get('name', 'AIAutoReply')}] 插件已加载")
    logger.info(f"私聊模式: {'开启' if pluginConfig.get('settings', {}).get('enablePrivateChat', True) else '关闭'}")
    logger.info(f"已启用的群聊: {pluginConfig.get('settings', {}).get('enabledGroups', [])}")

async def onUnload():
    conversation_history.clear()
    logger.info(f"[{pluginConfig.get('name', 'AIAutoReply')}] 插件已卸载")

@messageHandle(type=EventType.TEXT_MESSAGE)
async def handle_text_message(data: dict):
    settings = pluginConfig.get('settings', {})
    message_data = data.get('message', {}).get('data')

    msg_content = message_data.get('content', '').strip()
    robotId = data.get('wxid', '')
    sender = message_data.get('sender', '')
    if robotId == sender:
        return
    receiver = message_data.get('receiver', '')
    conversation_id = message_data.get('conversation_id', '')
    at_list = message_data.get('at_list', [])

    # 判断是群聊还是私聊
    is_group = conversation_id.startswith('R:')

    if is_group:
        # 群聊处理
        enabled_groups = settings.get('enabledGroups', [])
        if not enabled_groups or conversation_id not in enabled_groups:
            return

        # 检查是否@了机器人
        if settings.get('requireAtInGroup', True):
            bot_mentioned = any(at.get('user_id') == receiver for at in at_list)
            if not bot_mentioned:
                return

        chat_id = conversation_id
        reply_target = conversation_id
    else:
        # 私聊处理
        if not settings.get('enablePrivateChat', True):
            return

        chat_id = conversation_id
        reply_target = conversation_id

    if not msg_content:
        return

    # 获取AI回复
    reply = await get_ai_reply(chat_id, msg_content, settings)

    if reply:
        if is_group:
            await bot.sendAtText(robotId, reply_target, ' ' + reply, [sender])
        else:
            await bot.sendText(robotId, reply_target, reply)

async def get_ai_reply(chat_id: str, user_message: str, settings: dict) -> str:
    api_key = settings.get('apiKey', '')
    api_url = settings.get('apiUrl', 'https://api.deepseek.com/v1/chat/completions')
    model = settings.get('model', 'deepseek-chat')
    system_prompt = settings.get('systemPrompt', '你是一个友好的AI助手。')
    context_rounds = settings.get('contextRounds', 5)

    # 初始化对话历史
    if chat_id not in conversation_history:
        conversation_history[chat_id] = []

    # 添加用户消息
    conversation_history[chat_id].append({"role": "user", "content": user_message})

    # 保持上下文轮数限制
    if context_rounds > 0:
        max_messages = context_rounds * 2
        if len(conversation_history[chat_id]) > max_messages:
            conversation_history[chat_id] = conversation_history[chat_id][-max_messages:]

    # 构建消息列表
    messages = [{"role": "system", "content": system_prompt}] + conversation_history[chat_id]

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                api_url,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": model,
                    "messages": messages,
                },
                timeout=aiohttp.ClientTimeout(total=30)
            ) as response:
                if response.status == 200:
                    result = await response.json()
                    ai_reply = result['choices'][0]['message']['content']

                    # 添加AI回复到历史
                    conversation_history[chat_id].append({"role": "assistant", "content": ai_reply})

                    return ai_reply
                else:
                    error_text = await response.text()
                    logger.error(f"DeepSeek API错误: {response.status} - {error_text}")
                    return None
    except Exception as e:
        logger.error(f"调用DeepSeek API失败: {e}")
        return None
