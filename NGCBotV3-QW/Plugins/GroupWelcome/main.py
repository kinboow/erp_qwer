from loguru import logger
from Core.EventDispatcher import messageHandle
from Core.EVentType import EventType
from NGCBotApi import NGCBotApi

bot = NGCBotApi()
pluginConfig = {}

async def onLoad():
    logger.info(f"[{pluginConfig.get('name', 'GroupWelcome')}] 插件已加载")
    logger.info(f"已启用的群聊: {pluginConfig.get('settings', {}).get('enabledGroups', [])}")

async def onUnload():
    logger.info(f"[{pluginConfig.get('name', 'GroupWelcome')}] 插件已卸载")

@messageHandle(type=EventType.GROUP_MEMBER_ADD)
async def handle_group_member_add(data: dict):
    settings = pluginConfig.get('settings', {})
    message_data = data.get('message', {}).get('data', {})

    group_id = message_data.get('group_id', '')
    new_members = message_data.get('new_members', [])
    robotId = data.get('wxid', '')

    if not robotId:
        robotId = message_data.get('receiver', '')

    # 检查是否在启用的群聊列表中
    enabled_groups = settings.get('enabledGroups', [])
    if not enabled_groups or group_id not in enabled_groups:
        return

    # 获取欢迎消息模板
    welcome_template = settings.get('welcomeMessage', '欢迎 {name} 加入本群！')

    # 为每个新成员发送欢迎消息
    for member in new_members:
        member_name = member.get('name', '新成员')
        member_id = member.get('user_id', '')

        # 替换占位符
        welcome_msg = welcome_template.replace('{name}', member_name)

        # @新成员发送欢迎消息
        await bot.sendAtText(robotId, group_id, ' ' + welcome_msg, [member_id])

        logger.info(f"发送欢迎消息到群 {group_id}，新成员: {member_name}")
