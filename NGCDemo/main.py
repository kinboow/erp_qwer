# -*- coding: utf-8 -*-
"""
NGCDemo插件 - 集成所有事件类型的示例
作者: 云山
说明: 本插件演示如何处理所有EventType中定义的事件
"""

from loguru import logger
from NGCBotApi import NGCBotApi
from Core.EventDispatcher import messageHandle
from Core.EVentType import EventType, WxType

# 初始化Bot API
bot = NGCBotApi()

# 插件配置（由插件管理器注入）
pluginConfig = {}


# ==================== 消息类事件 ====================

@messageHandle(type=EventType.TEXT_MESSAGE)
async def onTextMessage(data: dict):
    """处理文本消息事件 (11046)"""
    try:
        wxid = data.get('wxid', '')
        message = data.get('message', {})
        messageData = message.get('data', {})

        msg = messageData.get('msg', '')
        fromWxid = messageData.get('from_wxid', '')
        roomWxid = messageData.get('room_wxid', '')
        wxType = messageData.get('wx_type', '')

        logger.info(f"[文本消息] 内容: {msg}")
        logger.debug(f"  机器人: {wxid}, 发送者: {fromWxid}, 群聊: {roomWxid}, wx_type: {wxType}")

        # 示例：回复消息
        # if msg == "hello":
        #     targetWxid = roomWxid if roomWxid else fromWxid
        #     await bot.sendText(robotId=wxid, receive=targetWxid, content="你好！")

    except Exception as e:
        logger.error(f"[文本消息] 处理失败: {e}", exc_info=True)


@messageHandle(type=EventType.IMAGE_MESSAGE)
async def onImageMessage(data: dict):
    """处理图片消息事件 (11047)"""
    try:
        wxid = data.get('wxid', '')
        message = data.get('message', {})
        messageData = message.get('data', {})

        fromWxid = messageData.get('from_wxid', '')
        roomWxid = messageData.get('room_wxid', '')
        imagePath = messageData.get('image', '')

        logger.info(f"[图片消息] 发送者: {fromWxid}, 图片路径: {imagePath}")
        logger.debug(f"  机器人: {wxid}, 群聊: {roomWxid}")

    except Exception as e:
        logger.error(f"[图片消息] 处理失败: {e}", exc_info=True)


@messageHandle(type=EventType.VOICE_MESSAGE)
async def onVoiceMessage(data: dict):
    """处理语音消息事件 (11048)"""
    try:
        wxid = data.get('wxid', '')
        message = data.get('message', {})
        messageData = message.get('data', {})

        fromWxid = messageData.get('from_wxid', '')
        roomWxid = messageData.get('room_wxid', '')
        voicePath = messageData.get('voice', '')

        logger.info(f"[语音消息] 发送者: {fromWxid}, 语音路径: {voicePath}")
        logger.debug(f"  机器人: {wxid}, 群聊: {roomWxid}")

    except Exception as e:
        logger.error(f"[语音消息] 处理失败: {e}", exc_info=True)


@messageHandle(type=EventType.VIDEO_MESSAGE)
async def onVideoMessage(data: dict):
    """处理视频消息事件 (11051)"""
    try:
        wxid = data.get('wxid', '')
        message = data.get('message', {})
        messageData = message.get('data', {})

        fromWxid = messageData.get('from_wxid', '')
        roomWxid = messageData.get('room_wxid', '')
        videoPath = messageData.get('video', '')

        logger.info(f"[视频消息] 发送者: {fromWxid}, 视频路径: {videoPath}")
        logger.debug(f"  机器人: {wxid}, 群聊: {roomWxid}")

    except Exception as e:
        logger.error(f"[视频消息] 处理失败: {e}", exc_info=True)


@messageHandle(type=EventType.EMOJI_MESSAGE)
async def onEmojiMessage(data: dict):
    """处理表情消息事件 (11052)"""
    try:
        wxid = data.get('wxid', '')
        message = data.get('message', {})
        messageData = message.get('data', {})

        fromWxid = messageData.get('from_wxid', '')
        roomWxid = messageData.get('room_wxid', '')
        emojiMd5 = messageData.get('emoji_md5', '')

        logger.info(f"[表情消息] 发送者: {fromWxid}, 表情MD5: {emojiMd5}")
        logger.debug(f"  机器人: {wxid}, 群聊: {roomWxid}")

    except Exception as e:
        logger.error(f"[表情消息] 处理失败: {e}", exc_info=True)


@messageHandle(type=EventType.LOCATION_MESSAGE)
async def onLocationMessage(data: dict):
    """处理位置消息事件 (11053)"""
    try:
        wxid = data.get('wxid', '')
        message = data.get('message', {})
        messageData = message.get('data', {})

        fromWxid = messageData.get('from_wxid', '')
        roomWxid = messageData.get('room_wxid', '')
        location = messageData.get('location', '')

        logger.info(f"[位置消息] 发送者: {fromWxid}, 位置: {location}")
        logger.debug(f"  机器人: {wxid}, 群聊: {roomWxid}")

    except Exception as e:
        logger.error(f"[位置消息] 处理失败: {e}", exc_info=True)


@messageHandle(type=EventType.CARD_MESSAGE)
async def onCardMessage(data: dict):
    """处理名片消息事件 (11050)"""
    try:
        wxid = data.get('wxid', '')
        message = data.get('message', {})
        messageData = message.get('data', {})

        fromWxid = messageData.get('from_wxid', '')
        roomWxid = messageData.get('room_wxid', '')
        cardWxid = messageData.get('card_wxid', '')
        cardNickname = messageData.get('card_nickname', '')

        logger.info(f"[名片消息] 发送者: {fromWxid}, 名片: {cardNickname} ({cardWxid})")
        logger.debug(f"  机器人: {wxid}, 群聊: {roomWxid}")

    except Exception as e:
        logger.error(f"[名片消息] 处理失败: {e}", exc_info=True)


@messageHandle(type=EventType.LINK_MESSAGE)
async def onLinkMessage(data: dict):
    """处理链接消息事件 (11048)"""
    try:
        wxid = data.get('wxid', '')
        message = data.get('message', {})
        messageData = message.get('data', {})

        fromWxid = messageData.get('from_wxid', '')
        roomWxid = messageData.get('room_wxid', '')
        title = messageData.get('title', '')
        url = messageData.get('url', '')

        logger.info(f"[链接消息] 发送者: {fromWxid}, 标题: {title}, URL: {url}")
        logger.debug(f"  机器人: {wxid}, 群聊: {roomWxid}")

    except Exception as e:
        logger.error(f"[链接消息] 处理失败: {e}", exc_info=True)


@messageHandle(type=EventType.FILE_MESSAGE)
async def onFileMessage(data: dict):
    """处理文件消息事件 (11055)"""
    try:
        wxid = data.get('wxid', '')
        message = data.get('message', {})
        messageData = message.get('data', {})

        fromWxid = messageData.get('from_wxid', '')
        roomWxid = messageData.get('room_wxid', '')
        fileName = messageData.get('file_name', '')
        fileSize = messageData.get('file_size', 0)

        logger.info(f"[文件消息] 发送者: {fromWxid}, 文件: {fileName}, 大小: {fileSize}")
        logger.debug(f"  机器人: {wxid}, 群聊: {roomWxid}")

    except Exception as e:
        logger.error(f"[文件消息] 处理失败: {e}", exc_info=True)


@messageHandle(type=EventType.APP_MESSAGE)
async def onAppMessage(data: dict):
    """处理小程序消息事件 (11056)"""
    try:
        wxid = data.get('wxid', '')
        message = data.get('message', {})
        messageData = message.get('data', {})

        fromWxid = messageData.get('from_wxid', '')
        roomWxid = messageData.get('room_wxid', '')
        appName = messageData.get('app_name', '')

        logger.info(f"[小程序消息] 发送者: {fromWxid}, 小程序: {appName}")
        logger.debug(f"  机器人: {wxid}, 群聊: {roomWxid}")

    except Exception as e:
        logger.error(f"[小程序消息] 处理失败: {e}", exc_info=True)


@messageHandle(type=EventType.TRANSFER_MESSAGE)
async def onTransferMessage(data: dict):
    """处理转账消息事件 (11057)"""
    try:
        wxid = data.get('wxid', '')
        message = data.get('message', {})
        messageData = message.get('data', {})

        fromWxid = messageData.get('from_wxid', '')
        roomWxid = messageData.get('room_wxid', '')
        amount = messageData.get('amount', 0)

        logger.info(f"[转账消息] 发送者: {fromWxid}, 金额: {amount}")
        logger.debug(f"  机器人: {wxid}, 群聊: {roomWxid}")

    except Exception as e:
        logger.error(f"[转账消息] 处理失败: {e}", exc_info=True)


@messageHandle(type=EventType.SYSTEM_MESSAGE)
async def onSystemMessage(data: dict):
    """处理系统消息事件 (11058)"""
    try:
        wxid = data.get('wxid', '')
        message = data.get('message', {})
        messageData = message.get('data', {})

        fromWxid = messageData.get('from_wxid', '')
        roomWxid = messageData.get('room_wxid', '')
        msg = messageData.get('msg', '')

        logger.info(f"[系统消息] 内容: {msg}")
        logger.debug(f"  机器人: {wxid}, 发送者: {fromWxid}, 群聊: {roomWxid}")

    except Exception as e:
        logger.error(f"[系统消息] 处理失败: {e}", exc_info=True)


@messageHandle(type=EventType.REVOKE_MESSAGE)
async def onRevokeMessage(data: dict):
    """处理撤回消息事件 (11059)"""
    try:
        wxid = data.get('wxid', '')
        message = data.get('message', {})
        messageData = message.get('data', {})

        fromWxid = messageData.get('from_wxid', '')
        roomWxid = messageData.get('room_wxid', '')
        msgid = messageData.get('msgid', '')

        logger.info(f"[撤回消息] 发送者: {fromWxid}, 消息ID: {msgid}")
        logger.debug(f"  机器人: {wxid}, 群聊: {roomWxid}")

    except Exception as e:
        logger.error(f"[撤回消息] 处理失败: {e}", exc_info=True)


@messageHandle(type=EventType.QRCODE_MESSAGE)
async def onQrcodeMessage(data: dict):
    """处理二维码收款事件 (11095)"""
    try:
        wxid = data.get('wxid', '')
        message = data.get('message', {})
        messageData = message.get('data', {})

        fromWxid = messageData.get('from_wxid', '')
        roomWxid = messageData.get('room_wxid', '')
        qrcodeUrl = messageData.get('qrcode_url', '')

        logger.info(f"[二维码收款] 发送者: {fromWxid}, 二维码: {qrcodeUrl}")
        logger.debug(f"  机器人: {wxid}, 群聊: {roomWxid}")

    except Exception as e:
        logger.error(f"[二维码收款] 处理失败: {e}", exc_info=True)


@messageHandle(type=EventType.OUTHERAPP_MESSAGE)
async def onOutherAppMessage(data: dict):
    """处理其它应用型消息事件 (11061)"""
    try:
        wxid = data.get('wxid', '')
        message = data.get('message', {})
        messageData = message.get('data', {})

        fromWxid = messageData.get('from_wxid', '')
        roomWxid = messageData.get('room_wxid', '')
        appType = messageData.get('app_type', '')

        logger.info(f"[其它应用消息] 发送者: {fromWxid}, 应用类型: {appType}")
        logger.debug(f"  机器人: {wxid}, 群聊: {roomWxid}")

    except Exception as e:
        logger.error(f"[其它应用消息] 处理失败: {e}", exc_info=True)


# ==================== 好友相关事件 ====================

@messageHandle(type=EventType.FRIEND_REQUEST)
async def onFriendRequest(data: dict):
    """处理好友请求事件 (11049)"""
    try:
        wxid = data.get('wxid', '')
        message = data.get('message', {})
        messageData = message.get('data', {})

        fromWxid = messageData.get('from_wxid', '')
        nickname = messageData.get('nickname', '')
        v3 = messageData.get('v3', '')
        v4 = messageData.get('v4', '')

        logger.info(f"[好友请求] 来自: {nickname} ({fromWxid})")
        logger.debug(f"  机器人: {wxid}, v3: {v3}, v4: {v4}")

        # 示例：自动通过好友请求
        # await bot.agreeFriendRequest(robotId=wxid, v3=v3, v4=v4)

    except Exception as e:
        logger.error(f"[好友请求] 处理失败: {e}", exc_info=True)


@messageHandle(type=EventType.FRIENDADD_EVENT)
async def onFriendAdd(data: dict):
    """处理好友新增事件 (11102)"""
    try:
        wxid = data.get('wxid', '')
        message = data.get('message', {})
        messageData = message.get('data', {})

        friendWxid = messageData.get('friend_wxid', '')
        nickname = messageData.get('nickname', '')

        logger.info(f"[好友新增] 新好友: {nickname} ({friendWxid})")
        logger.debug(f"  机器人: {wxid}")

    except Exception as e:
        logger.error(f"[好友新增] 处理失败: {e}", exc_info=True)


@messageHandle(type=EventType.FRIENDDEL_EVENT)
async def onFriendDel(data: dict):
    """处理好友删除事件 (11103)"""
    try:
        wxid = data.get('wxid', '')
        message = data.get('message', {})
        messageData = message.get('data', {})

        friendWxid = messageData.get('friend_wxid', '')

        logger.info(f"[好友删除] 删除好友: {friendWxid}")
        logger.debug(f"  机器人: {wxid}")

    except Exception as e:
        logger.error(f"[好友删除] 处理失败: {e}", exc_info=True)


# ==================== 群聊相关事件 ====================

@messageHandle(type=EventType.GROUPADD_EVENT)
async def onGroupAdd(data: dict):
    """处理群成员新增事件 (11098)"""
    try:
        wxid = data.get('wxid', '')
        message = data.get('message', {})
        messageData = message.get('data', {})

        roomWxid = messageData.get('room_wxid', '')
        memberWxid = messageData.get('member_wxid', '')
        inviterWxid = messageData.get('inviter_wxid', '')

        logger.info(f"[群成员新增] 群: {roomWxid}, 新成员: {memberWxid}, 邀请人: {inviterWxid}")
        logger.debug(f"  机器人: {wxid}")

    except Exception as e:
        logger.error(f"[群成员新增] 处理失败: {e}", exc_info=True)


@messageHandle(type=EventType.GROUPDEL_EVENT)
async def onGroupDel(data: dict):
    """处理群成员退出事件 (11099)"""
    try:
        wxid = data.get('wxid', '')
        message = data.get('message', {})
        messageData = message.get('data', {})

        roomWxid = messageData.get('room_wxid', '')
        memberWxid = messageData.get('member_wxid', '')

        logger.info(f"[群成员退出] 群: {roomWxid}, 退出成员: {memberWxid}")
        logger.debug(f"  机器人: {wxid}")

    except Exception as e:
        logger.error(f"[群成员退出] 处理失败: {e}", exc_info=True)


@messageHandle(type=EventType.GROUPCREATE_EVENT)
async def onGroupCreate(data: dict):
    """处理群创建成功事件 (11100)"""
    try:
        wxid = data.get('wxid', '')
        message = data.get('message', {})
        messageData = message.get('data', {})

        roomWxid = messageData.get('room_wxid', '')
        roomName = messageData.get('room_name', '')

        logger.info(f"[群创建成功] 群名: {roomName}, 群ID: {roomWxid}")
        logger.debug(f"  机器人: {wxid}")

    except Exception as e:
        logger.error(f"[群创建成功] 处理失败: {e}", exc_info=True)


@messageHandle(type=EventType.GROUPKICK_EVENT)
async def onGroupKick(data: dict):
    """处理退群或被踢事件 (11101)"""
    try:
        wxid = data.get('wxid', '')
        message = data.get('message', {})
        messageData = message.get('data', {})

        roomWxid = messageData.get('room_wxid', '')
        kickType = messageData.get('kick_type', '')  # 1=主动退群, 2=被踢

        logger.info(f"[退群/被踢] 群: {roomWxid}, 类型: {kickType}")
        logger.debug(f"  机器人: {wxid}")

    except Exception as e:
        logger.error(f"[退群/被踢] 处理失败: {e}", exc_info=True)


# ==================== 系统状态事件 ====================

@messageHandle(type=EventType.WINDOW_STATE_CHANGE)
async def onWindowStateChange(data: dict):
    """处理窗口状态变化事件 (11088)"""
    try:
        wxid = data.get('wxid', '')
        message = data.get('message', {})
        messageData = message.get('data', {})

        state = messageData.get('state', '')

        logger.info(f"[窗口状态变化] 状态: {state}")
        logger.debug(f"  机器人: {wxid}")

    except Exception as e:
        logger.error(f"[窗口状态变化] 处理失败: {e}", exc_info=True)


@messageHandle(type=EventType.CHAT_OBJECT_CHANGE)
async def onChatObjectChange(data: dict):
    """处理聊天对象变化事件 (11091)"""
    try:
        wxid = data.get('wxid', '')
        message = data.get('message', {})
        messageData = message.get('data', {})

        chatWxid = messageData.get('chat_wxid', '')

        logger.info(f"[聊天对象变化] 当前聊天: {chatWxid}")
        logger.debug(f"  机器人: {wxid}")

    except Exception as e:
        logger.error(f"[聊天对象变化] 处理失败: {e}", exc_info=True)


@messageHandle(type=EventType.API_READY)
async def onApiReady(data: dict):
    """处理接口就绪事件 (11024)"""
    try:
        wxid = data.get('wxid', '')
        message = data.get('message', {})
        messageData = message.get('data', {})

        logger.success(f"[接口就绪] 机器人: {wxid}")
        logger.debug(f"  数据: {messageData}")

    except Exception as e:
        logger.error(f"[接口就绪] 处理失败: {e}", exc_info=True)


@messageHandle(type=EventType.QRCODE_EVENT)
async def onQrcodeEvent(data: dict):
    """处理登录二维码事件 (11087)"""
    try:
        wxid = data.get('wxid', '')
        message = data.get('message', {})
        messageData = message.get('data', {})

        qrcodePath = messageData.get('qrcode_path', '')

        logger.info(f"[登录二维码] 二维码路径: {qrcodePath}")
        logger.debug(f"  机器人: {wxid}")

    except Exception as e:
        logger.error(f"[登录二维码] 处理失败: {e}", exc_info=True)


@messageHandle(type=EventType.LOGIN_EVENT)
async def onLogin(data: dict):
    """处理登录成功事件 (11025)"""
    try:
        wxid = data.get('wxid', '')
        message = data.get('message', {})
        messageData = message.get('data', {})

        nickname = messageData.get('nickname', '')

        logger.success(f"[登录成功] 机器人: {nickname} ({wxid})")
        logger.debug(f"  数据: {messageData}")

    except Exception as e:
        logger.error(f"[登录成功] 处理失败: {e}", exc_info=True)


@messageHandle(type=EventType.LOGOUT_EVENT)
async def onLogout(data: dict):
    """处理用户注销事件 (11026)"""
    try:
        wxid = data.get('wxid', '')
        message = data.get('message', {})
        messageData = message.get('data', {})

        logger.warning(f"[用户注销] 机器人: {wxid}")
        logger.debug(f"  数据: {messageData}")

    except Exception as e:
        logger.error(f"[用户注销] 处理失败: {e}", exc_info=True)


# ==================== 插件生命周期 ====================

async def onLoad():
    """插件加载时调用"""
    logger.success("=" * 60)
    logger.success("NGCDemo插件已加载")
    logger.success("作者: 云山")
    logger.success("说明: 本插件集成了所有EventType事件的处理示例")
    logger.success("=" * 60)
    logger.info("已注册的事件类型:")
    logger.info("  消息类: 文本、图片、语音、视频、表情、位置、名片、链接、文件、小程序、转账、系统、撤回、二维码、其它应用")
    logger.info("  好友类: 好友请求、好友新增、好友删除")
    logger.info("  群聊类: 群成员新增、群成员退出、群创建、退群/被踢")
    logger.info("  系统类: 窗口状态变化、聊天对象变化、接口就绪、登录二维码、登录成功、用户注销")
    logger.success("=" * 60)


async def onUnload():
    """插件卸载时调用"""
    logger.info("NGCDemo插件已卸载")

