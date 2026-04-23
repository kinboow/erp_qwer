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
    """处理文本消息通知 (11041)"""
    try:
        message = data.get('message', {})
        messageData = message.get('data', {})
        content = messageData.get('content', '')
        contentType = messageData.get('content_type', '')
        conversationId = messageData.get('conversation_id', '')
        sender = messageData.get('sender', '')
        senderName = messageData.get('sender_name', '')
        robotId = data.get('wxid', '')
        sendTime = messageData.get('send_time', '')
        atList = messageData.get('at_list', [])

        logger.info(f"[文本消息] {senderName}: {content}")
        logger.debug(f"  会话: {conversationId}, 发送者: {sender}, 接收者: {robotId}")
        logger.debug(f"  内容类型: {contentType}, 时间: {sendTime}, @列表: {atList}")

        # 示例：回复消息
        # if content == "hello":
        #     await bot.sendText(robotId=robotId, receive=conversationId, content="你好！")

    except Exception as e:
        logger.error(f"[文本消息] 处理失败: {e}", exc_info=True)


@messageHandle(type=EventType.IMAGE_MESSAGE)
async def onImageMessage(data: dict):
    """处理图片消息通知 (11042)"""
    try:
        message = data.get('message', {})
        messageData = message.get('data', {})
        contentType = messageData.get('content_type', '')
        conversationId = messageData.get('conversation_id', '')
        sender = messageData.get('sender', '')
        senderName = messageData.get('sender_name', '')
        robotId = data.get('wxid', '')
        cdnType = messageData.get('cdn_type', '')
        cdn = messageData.get('cdn', {})
        
        md5 = cdn.get('md5', '')
        size = cdn.get('size', 0)

        logger.info(f"[图片消息] {senderName} 发送图片")
        logger.debug(f"  会话: {conversationId}, CDN类型: {cdnType}")
        logger.debug(f"  MD5: {md5}, 大小: {size} bytes")

    except Exception as e:
        logger.error(f"[图片消息] 处理失败: {e}", exc_info=True)


@messageHandle(type=EventType.VOICE_MESSAGE)
async def onVoiceMessage(data: dict):
    """处理语音消息通知 (11044)"""
    try:
        message = data.get('message', {})
        messageData = message.get('data', {})
        conversationId = messageData.get('conversation_id', '')
        senderName = messageData.get('sender_name', '')
        duration = messageData.get('duration', 0)
        c2cCdn = messageData.get('c2c_cdn', {})
        voiceTime = c2cCdn.get('voice_time', 0)

        logger.info(f"[语音消息] {senderName} 发送语音: {duration}秒")
        logger.debug(f"  会话: {conversationId}")

    except Exception as e:
        logger.error(f"[语音消息] 处理失败: {e}", exc_info=True)


@messageHandle(type=EventType.VIDEO_MESSAGE)
async def onVideoMessage(data: dict):
    """处理视频消息通知 (11043)"""
    try:
        message = data.get('message', {})
        messageData = message.get('data', {})
        conversationId = messageData.get('conversation_id', '')
        senderName = messageData.get('sender_name', '')
        duration = messageData.get('duration', 0)
        fileSize = messageData.get('file_size', 0)
        cdnType = messageData.get('cdn_type', '')

        logger.info(f"[视频消息] {senderName} 发送视频: {duration}秒, {fileSize}bytes")
        logger.debug(f"  会话: {conversationId}, CDN类型: {cdnType}")

    except Exception as e:
        logger.error(f"[视频消息] 处理失败: {e}", exc_info=True)


@messageHandle(type=EventType.GIF_MESSAGE)
async def onGifMessage(data: dict):
    """处理GIF消息通知 (11048)"""
    try:
        message = data.get('message', {})
        messageData = message.get('data', {})
        conversationId = messageData.get('conversation_id', '')
        senderName = messageData.get('sender_name', '')
        name = messageData.get('name', '')
        url = messageData.get('url', '')
        height = messageData.get('height', 0)
        width = messageData.get('width', 0)

        logger.info(f"[GIF消息] {senderName}: {name}")
        logger.debug(f"  会话: {conversationId}, 尺寸: {width}x{height}")

    except Exception as e:
        logger.error(f"[GIF消息] 处理失败: {e}", exc_info=True)


@messageHandle(type=EventType.LOCATION_MESSAGE)
async def onLocationMessage(data: dict):
    """处理位置消息通知 (11046)"""
    try:
        message = data.get('message', {})
        messageData = message.get('data', {})
        conversationId = messageData.get('conversation_id', '')
        senderName = messageData.get('sender_name', '')
        title = messageData.get('title', '')
        address = messageData.get('address', '')
        latitude = messageData.get('latitude', 0)
        longitude = messageData.get('longitude', 0)

        logger.info(f"[位置消息] {senderName}: {title}")
        logger.debug(f"  会话: {conversationId}, 地址: {address}")
        logger.debug(f"  经纬度: ({latitude}, {longitude})")

    except Exception as e:
        logger.error(f"[位置消息] 处理失败: {e}", exc_info=True)


@messageHandle(type=EventType.CARD_MESSAGE)
async def onCardMessage(data: dict):
    """处理名片消息通知 (11050)"""
    try:
        message = data.get('message', {})
        messageData = message.get('data', {})
        conversationId = messageData.get('conversation_id', '')
        senderName = messageData.get('sender_name', '')
        nickname = messageData.get('nickname', '')
        userId = messageData.get('user_id', '')
        source = messageData.get('source', '')

        logger.info(f"[名片消息] {senderName} 发送名片: {nickname} ({userId})")
        logger.debug(f"  会话: {conversationId}, 来源: {source}")

    except Exception as e:
        logger.error(f"[名片消息] 处理失败: {e}", exc_info=True)


@messageHandle(type=EventType.LINK_MESSAGE)
async def onLinkMessage(data: dict):
    """处理链接消息通知 (11047)"""
    try:
        message = data.get('message', {})
        messageData = message.get('data', {})
        conversationId = messageData.get('conversation_id', '')
        senderName = messageData.get('sender_name', '')
        title = messageData.get('title', '')
        url = messageData.get('url', '')
        desc = messageData.get('desc', '')

        logger.info(f"[链接消息] {senderName}: {title}")
        logger.debug(f"  会话: {conversationId}, URL: {url}")

    except Exception as e:
        logger.error(f"[链接消息] 处理失败: {e}", exc_info=True)


@messageHandle(type=EventType.FILE_MESSAGE)
async def onFileMessage(data: dict):
    """处理文件消息通知 (11045)"""
    try:
        message = data.get('message', {})
        messageData = message.get('data', {})
        conversationId = messageData.get('conversation_id', '')
        senderName = messageData.get('sender_name', '')
        cdn = messageData.get('cdn', {})
        fileName = cdn.get('file_name', '')
        fileSize = cdn.get('size', 0)
        md5 = cdn.get('md5', '')

        logger.info(f"[文件消息] {senderName}: {fileName} ({fileSize}bytes)")
        logger.debug(f"  会话: {conversationId}, MD5: {md5}")

    except Exception as e:
        logger.error(f"[文件消息] 处理失败: {e}", exc_info=True)


@messageHandle(type=EventType.MINIPROGRAM_MESSAGE)
async def onMiniprogramMessage(data: dict):
    """处理小程序消息通知 (11066)"""
    try:
        message = data.get('message', {})
        messageData = message.get('data', {})
        conversationId = messageData.get('conversation_id', '')
        senderName = messageData.get('sender_name', '')
        appname = messageData.get('appname', '')
        title = messageData.get('title', '')
        pagePath = messageData.get('page_path', '')

        logger.info(f"[小程序消息] {senderName}: {appname} - {title}")
        logger.debug(f"  会话: {conversationId}, 页面: {pagePath}")

    except Exception as e:
        logger.error(f"[小程序消息] 处理失败: {e}", exc_info=True)


@messageHandle(type=EventType.REDPACKET_MESSAGE)
async def onRedpacketMessage(data: dict):
    """处理红包消息通知 (11049)"""
    try:
        message = data.get('message', {})
        messageData = message.get('data', {})
        conversationId = messageData.get('conversation_id', '')
        senderName = messageData.get('sender_name', '')
        money = messageData.get('money', 0)
        remark = messageData.get('remark', '')

        logger.info(f"[红包消息] {senderName} 发送红包: {money}元")
        logger.debug(f"  会话: {conversationId}, 备注: {remark}")

    except Exception as e:
        logger.error(f"[红包消息] 处理失败: {e}", exc_info=True)


@messageHandle(type=EventType.IMAGE_TEXT_MESSAGE)
async def onImageTextMessage(data: dict):
    """处理图文消息通知 (11068)"""
    try:
        message = data.get('message', {})
        messageData = message.get('data', {})
        conversationId = messageData.get('conversation_id', '')
        senderName = messageData.get('sender_name', '')
        textContent = messageData.get('text_content', '')
        imageList = messageData.get('image_list', [])

        logger.info(f"[图文消息] {senderName}: {textContent}")
        logger.debug(f"  会话: {conversationId}, 图片数: {len(imageList)}")

    except Exception as e:
        logger.error(f"[图文消息] 处理失败: {e}", exc_info=True)


@messageHandle(type=EventType.VIDEO_CHANNEL_MESSAGE)
async def onVideoChannelMessage(data: dict):
    """处理视频号消息通知 (11124)"""
    try:
        message = data.get('message', {})
        messageData = message.get('data', {})
        conversationId = messageData.get('conversation_id', '')
        senderName = messageData.get('sender_name', '')
        nickname = messageData.get('nickname', '')
        desc = messageData.get('desc', '')
        feedType = messageData.get('feed_type', 0)

        logger.info(f"[视频号消息] {senderName} 分享视频号: {nickname}")
        logger.debug(f"  会话: {conversationId}, 类型: {feedType}")
        logger.debug(f"  描述: {desc[:50]}..." if len(desc) > 50 else f"  描述: {desc}")

    except Exception as e:
        logger.error(f"[视频号消息] 处理失败: {e}", exc_info=True)


@messageHandle(type=EventType.VIDEO_CHANNEL_LIVE_MESSAGE)
async def onVideoChannelLiveMessage(data: dict):
    """处理视频号直播消息通知 (11195)"""
    try:
        message = data.get('message', {})
        messageData = message.get('data', {})
        conversationId = messageData.get('conversation_id', '')
        senderName = messageData.get('sender_name', '')
        nickname = messageData.get('nickname', '')
        desc = messageData.get('desc', '')
        objectId = messageData.get('object_id', '')

        logger.info(f"[视频号直播] {senderName} 分享直播: {nickname}")
        logger.debug(f"  会话: {conversationId}, 直播ID: {objectId}")

    except Exception as e:
        logger.error(f"[视频号直播] 处理失败: {e}", exc_info=True)


@messageHandle(type=EventType.REVOKE_MESSAGE)
async def onRevokeMessage(data: dict):
    """处理撤回消息通知 (11123)"""
    try:
        message = data.get('message', {})
        messageData = message.get('data', {})
        messageServerId = messageData.get('message_server_id', '')
        opUserId = messageData.get('op_user_id', '')
        roomId = messageData.get('room_id', '')

        logger.info(f"[撤回消息] 撤回人: {opUserId}, 消息ID: {messageServerId}")
        logger.debug(f"  群ID: {roomId}")

    except Exception as e:
        logger.error(f"[撤回消息] 处理失败: {e}", exc_info=True)


# ==================== 好友事件通知 ====================

@messageHandle(type=EventType.FRIEND_REQUEST)
async def onFriendRequest(data: dict):
    """处理好友申请通知 (11063)"""
    try:
        message = data.get('message', {})
        messageData = message.get('data', {})
        userId = messageData.get('user_id', '')
        nickname = messageData.get('nickname', '')
        corpId = messageData.get('corp_id', '')
        sex = messageData.get('sex', 0)
        verify = messageData.get('verify', '')

        logger.info(f"[好友申请] 来自: {nickname} ({userId})")
        logger.debug(f"  公司ID: {corpId}, 性别: {sex}, 验证消息: {verify}")

    except Exception as e:
        logger.error(f"[好友申请] 处理失败: {e}", exc_info=True)


@messageHandle(type=EventType.FRIEND_ADD)
async def onFriendAdd(data: dict):
    """处理好友新增通知 (11076)"""
    try:
        message = data.get('message', {})
        messageData = message.get('data', {})
        userId = messageData.get('user_id', '')
        username = messageData.get('username', '')
        avatar = messageData.get('avatar', '')
        corpId = messageData.get('corp_id', '')

        logger.info(f"[好友新增] 新好友: {username} ({userId})")
        logger.debug(f"  公司ID: {corpId}")

    except Exception as e:
        logger.error(f"[好友新增] 处理失败: {e}", exc_info=True)


@messageHandle(type=EventType.FRIEND_DELETE)
async def onFriendDelete(data: dict):
    """处理好友删除通知 (11077)"""
    try:
        message = data.get('message', {})
        messageData = message.get('data', {})
        userId = messageData.get('user_id', '')
        nickname = messageData.get('nickname', '')
        corpId = messageData.get('corp_id', '')

        logger.info(f"[好友删除] 删除好友: {nickname} ({userId})")
        logger.debug(f"  公司ID: {corpId}")

    except Exception as e:
        logger.error(f"[好友删除] 处理失败: {e}", exc_info=True)


# ==================== 群聊事件通知 ====================

@messageHandle(type=EventType.GROUP_CREATE)
async def onGroupCreate(data: dict):
    """处理新增群通知 (11074)"""
    try:
        message = data.get('message', {})
        messageData = message.get('data', {})
        roomConversationId = messageData.get('room_conversation_id', '')
        roomName = messageData.get('room_name', '')
        opUserId = messageData.get('op_user_id', '')
        opUserName = messageData.get('op_user_name', '')
        memberList = messageData.get('member_list', [])

        logger.info(f"[新增群] 群名: {roomName}, 创建人: {opUserName}")
        logger.debug(f"  群ID: {roomConversationId}, 成员数: {len(memberList)}")

    except Exception as e:
        logger.error(f"[新增群] 处理失败: {e}", exc_info=True)


@messageHandle(type=EventType.GROUP_MEMBER_ADD)
async def onGroupMemberAdd(data: dict):
    """处理群成员增加通知 (11072)"""
    try:
        message = data.get('message', {})
        messageData = message.get('data', {})
        roomConversationId = messageData.get('room_conversation_id', '')
        roomName = messageData.get('room_name', '')
        opUserId = messageData.get('op_user_id', '')
        opUserName = messageData.get('op_user_name', '')
        memberList = messageData.get('member_list', [])

        logger.info(f"[群成员增加] 群: {roomName}, 邀请人: {opUserName}")
        logger.debug(f"  群ID: {roomConversationId}, 新成员: {memberList}")

    except Exception as e:
        logger.error(f"[群成员增加] 处理失败: {e}", exc_info=True)


@messageHandle(type=EventType.GROUP_MEMBER_DELETE)
async def onGroupMemberDelete(data: dict):
    """处理群成员减少通知 (11073)"""
    try:
        message = data.get('message', {})
        messageData = message.get('data', {})
        roomConversationId = messageData.get('room_conversation_id', '')
        roomName = messageData.get('room_name', '')
        opUserId = messageData.get('op_user_id', '')
        opUserName = messageData.get('op_user_name', '')
        memberList = messageData.get('member_list', [])

        logger.info(f"[群成员减少] 群: {roomName}, 操作人: {opUserName}")
        logger.debug(f"  群ID: {roomConversationId}, 移除成员: {memberList}")

    except Exception as e:
        logger.error(f"[群成员减少] 处理失败: {e}", exc_info=True)


@messageHandle(type=EventType.GROUP_QUIT)
async def onGroupQuit(data: dict):
    """处理主动退群通知 (11075)"""
    try:
        message = data.get('message', {})
        messageData = message.get('data', {})
        roomConversationId = messageData.get('room_conversation_id', '')
        roomName = messageData.get('room_name', '')
        opUserId = messageData.get('op_user_id', '')
        opUserName = messageData.get('op_user_name', '')

        logger.info(f"[主动退群] 群: {roomName}, 退群人: {opUserName}")
        logger.debug(f"  群ID: {roomConversationId}")

    except Exception as e:
        logger.error(f"[主动退群] 处理失败: {e}", exc_info=True)


@messageHandle(type=EventType.GROUP_NAME_CHANGE)
async def onGroupNameChange(data: dict):
    """处理群名称变化通知 (11078)"""
    try:
        message = data.get('message', {})
        messageData = message.get('data', {})
        roomConversationId = messageData.get('room_conversation_id', '')
        roomName = messageData.get('room_name', '')
        opUserId = messageData.get('op_user_id', '')

        logger.info(f"[群名称变化] 新群名: {roomName}")
        logger.debug(f"  群ID: {roomConversationId}, 操作人: {opUserId}")

    except Exception as e:
        logger.error(f"[群名称变化] 处理失败: {e}", exc_info=True)


# ==================== 插件生命周期 ====================

async def onLoad():
    """插件加载时调用"""
    logger.success("=" * 60)
    logger.success("NGCDemo插件已加载")
    logger.success("作者: 云山")
    logger.success("说明: 本插件演示如何处理接口文档中定义的所有消息通知事件")
    logger.success("=" * 60)
    logger.info("已注册的事件类型:")
    logger.info("  消息通知: 文本、图片、链接、GIF、文件、视频、语音、位置、名片")
    logger.info("           小程序、视频号、视频号直播、红包、图文、撤回")
    logger.info("  好友事件: 好友申请、好友新增、好友删除")
    logger.info("  群聊事件: 新增群、群成员增加、群成员减少、主动退群、群名称变化")
    logger.success("=" * 60)


async def onUnload():
    """插件卸载时调用"""
    logger.info("NGCDemo插件已卸载")

