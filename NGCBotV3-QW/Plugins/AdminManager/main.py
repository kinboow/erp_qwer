# -*- coding: utf-8 -*-

from loguru import logger
from NGCBotApi import NGCBotApi
from Core.EventDispatcher import messageHandle
from Core.EVentType import EventType, WxType
from Core.PluginManager import pluginManager

# 初始化Bot API
bot = NGCBotApi()

# 插件配置（由插件管理器注入）
pluginConfig = {}


def isAdmin(wxid: str) -> bool:
    """检查是否是管理员"""
    settings = pluginConfig.get('settings', {})
    adminList = settings.get('adminList', [])
    return wxid in adminList


def getCommandPrefix() -> str:
    """获取命令前缀"""
    settings = pluginConfig.get('settings', {})
    return settings.get('commandPrefix', '#')


def isAllowInGroup() -> bool:
    """是否允许在群聊中使用"""
    settings = pluginConfig.get('settings', {})
    return settings.get('allowInGroup', True)


@messageHandle(type=EventType.TEXT_MESSAGE)
async def onTextMessage(data: dict):
    """处理文本消息通知 - 管理员命令 (11041)"""
    try:
        messageData = data.get('message', {}).get('data', {})
        content = messageData.get('content', '').strip()
        conversationId = messageData.get('conversation_id', '')
        sender = messageData.get('sender', '')
        robotId = data.get('wxid', '')

        if not robotId:
            robotId = messageData.get('receiver', '')
        
        # 检查是否是管理员
        if not isAdmin(sender):
            logger.debug(f"非管理员用户: {sender}")
            return
        
        # 判断是否为群聊（conversation_id以R:开头表示群聊）
        isGroup = conversationId.startswith('R:')
        
        # 检查是否在群聊中，且是否允许
        if isGroup and not isAllowInGroup():
            return
        
        # 获取命令前缀
        prefix = getCommandPrefix()
        if not content.startswith(prefix):
            return
        
        # 解析命令
        command = content[len(prefix):].strip()
        parts = command.split()

        if not parts:
            return
        
        cmd = parts[0].lower()
        args = parts[1:] if len(parts) > 1 else []

        # 确定回复目标（使用conversation_id）
        logger.info(f"[管理员命令] 命令: {cmd}, 参数: {args}, 执行者: {sender}")

        # 执行命令
        if cmd == 'load':
            # 加载插件: #load PluginName
            if not args:
                await sendReply(robotId, conversationId, "❌ 用法: #load <插件名>")
                return

            pluginName = args[0]
            displayName = pluginManager.getPluginDisplayName(pluginName)
            success = await pluginManager.loadPlugin(pluginName)
            if success:
                await sendReply(robotId, conversationId, f"✅ 插件【{displayName}】加载成功")
            else:
                await sendReply(robotId, conversationId, f"❌ 插件【{displayName}】加载失败")

        elif cmd == 'unload':
            # 卸载插件: #unload PluginName
            if not args:
                await sendReply(robotId, conversationId, "❌ 用法: #unload <插件名>")
                return

            pluginName = args[0]

            # 不允许卸载管理员插件自己
            if pluginName == 'AdminManager':
                await sendReply(robotId, conversationId, "❌ 不能卸载管理员插件")
                return

            displayName = pluginManager.getPluginDisplayName(pluginName)
            success = await pluginManager.unloadPlugin(pluginName)
            if success:
                await sendReply(robotId, conversationId, f"✅ 插件【{displayName}】卸载成功")
            else:
                await sendReply(robotId, conversationId, f"❌ 插件【{displayName}】卸载失败")

        elif cmd == 'reload':
            # 重载插件: #reload PluginName
            if not args:
                await sendReply(robotId, conversationId, "❌ 用法: #reload <插件名>")
                return

            pluginName = args[0]
            displayName = pluginManager.getPluginDisplayName(pluginName)

            # 先卸载再加载
            await pluginManager.unloadPlugin(pluginName)
            success = await pluginManager.loadPlugin(pluginName)
            if success:
                await sendReply(robotId, conversationId, f"✅ 插件【{displayName}】重载成功")
            else:
                await sendReply(robotId, conversationId, f"❌ 插件【{displayName}】重载失败")
        
        elif cmd == 'list':
            # 列出所有插件: #list
            allPlugins = pluginManager.getAllPlugins()
            if allPlugins:
                loadedPlugins = [p for p in allPlugins if p['loaded']]
                unloadedPlugins = [p for p in allPlugins if not p['loaded']]

                msg = f"📋 插件列表 (共{len(allPlugins)}个)\n\n"

                if loadedPlugins:
                    msg += f"✅ 已加载 ({len(loadedPlugins)}):\n"
                    for p in loadedPlugins:
                        status = "🟢" if p['enabled'] else "🔴"
                        msg += f"{status} {p['displayName']}\n"

                if unloadedPlugins:
                    msg += f"\n⭕ 未加载 ({len(unloadedPlugins)}):\n"
                    for p in unloadedPlugins:
                        status = "🟢" if p['enabled'] else "🔴"
                        msg += f"{status} {p['displayName']}\n"

                await sendReply(robotId, conversationId, msg.strip())
            else:
                await sendReply(robotId, conversationId, "📋 插件目录为空")

        elif cmd == 'listall':
            # 列出所有插件（包括详细信息）: #listall
            allPlugins = pluginManager.getAllPlugins()
            if allPlugins:
                msg = f"📋 所有插件详情 (共{len(allPlugins)}个)\n\n"

                for p in allPlugins:
                    status = "✅已加载" if p['loaded'] else "⭕未加载"
                    enabled = "🟢启用" if p['enabled'] else "🔴禁用"
                    version = p.get('version', 'unknown')
                    author = p.get('author', 'unknown')

                    msg += f"【{p['displayName']}】\n"
                    msg += f"  状态: {status} | {enabled}\n"
                    msg += f"  版本: {version} | 作者: {author}\n"
                    msg += f"  目录: {p['name']}\n\n"

                await sendReply(robotId, conversationId, msg.strip())
            else:
                await sendReply(robotId, conversationId, "📋 插件目录为空")

        elif cmd == 'reloadall':
            # 重载所有插件: #reloadall
            await sendReply(robotId, conversationId, "🔄 开始重载所有插件...")
            successCount, failCount = await pluginManager.reloadAllPlugins()
            await sendReply(robotId, conversationId, f"✅ 重载完成\n成功: {successCount} | 失败: {failCount}")

        elif cmd == 'help':
            # 帮助信息: #help
            helpMsg = f"""🤖 管理员命令帮助

{prefix}load <插件名> - 加载插件
{prefix}unload <插件名> - 卸载插件
{prefix}reload <插件名> - 重载插件
{prefix}reloadall - 重载所有已加载插件
{prefix}list - 列出所有插件（简洁）
{prefix}listall - 列出所有插件（详细）
{prefix}help - 显示此帮助信息

说明:
• 🟢 表示插件已启用
• 🔴 表示插件已禁用
• ✅ 表示插件已加载
• ⭕ 表示插件未加载"""
            await sendReply(robotId, conversationId, helpMsg)
        
        else:
            await sendReply(robotId, conversationId, f"❌ 未知命令: {cmd}\n使用 {prefix}help 查看帮助")
        
    except Exception as e:
        logger.error(f"AdminManager处理失败: {e}", exc_info=True)


async def sendReply(robotId: str, targetWxid: str, content: str):
    """发送回复消息"""
    try:
        await bot.sendText(robotId=robotId, receive=targetWxid, content=content)
    except Exception as e:
        logger.error(f"发送消息失败: {e}", exc_info=True)


async def onLoad():
    """插件加载时调用"""
    logger.success("=" * 60)
    logger.success("AdminManager插件已加载")

    # 输出配置信息
    settings = pluginConfig.get('settings', {})
    adminList = settings.get('adminList', [])
    commandPrefix = settings.get('commandPrefix', '#')
    allowInGroup = settings.get('allowInGroup', True)

    logger.info(f"配置信息:")
    logger.info(f"  管理员数量: {len(adminList)}")
    logger.info(f"  命令前缀: {commandPrefix}")
    logger.info(f"  允许群聊: {allowInGroup}")
    logger.success("=" * 60)


async def onUnload():
    """插件卸载时调用"""
    logger.info("AdminManager插件已卸载")

