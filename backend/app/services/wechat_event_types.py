# -*- coding: utf-8 -*-
"""
企业微信消息事件类型与内容类型常量
学习自 NGCBotV3-QW Core/EVentType.py，适配 ERP 系统使用
"""


class EventType:
    """消息通知事件类型 - 对应 message.type 字段"""

    # ============ 系统通知 ============
    API_READY = 11024
    LOGIN_QRCODE = 11028
    LOGIN_QRCODE_STATUS = 11174
    LOGIN_SUCCESS = 11026
    LOGIN_SUCCESS_WITH_CORP = 11179
    LOGOUT = 11027

    # ============ 消息通知 ============
    TEXT_MESSAGE = 11041
    IMAGE_MESSAGE = 11042
    VIDEO_MESSAGE = 11043
    VOICE_MESSAGE = 11044
    FILE_MESSAGE = 11045
    LOCATION_MESSAGE = 11046
    LINK_MESSAGE = 11047
    GIF_MESSAGE = 11048
    REDPACKET_MESSAGE = 11049
    CARD_MESSAGE = 11050
    MINIPROGRAM_MESSAGE = 11066
    IMAGE_TEXT_MESSAGE = 11068
    REVOKE_MESSAGE = 11123
    VIDEO_CHANNEL_MESSAGE = 11124
    VIDEO_CHANNEL_LIVE_MESSAGE = 11195

    # ============ 好友事件 ============
    FRIEND_REQUEST = 11063
    FRIEND_ADD = 11076
    FRIEND_DELETE = 11077

    # ============ 群聊事件 ============
    GROUP_MEMBER_ADD = 11072
    GROUP_MEMBER_DELETE = 11073
    GROUP_CREATE = 11074
    GROUP_QUIT = 11075
    GROUP_NAME_CHANGE = 11078


class WxType:
    """消息内容类型 - 对应 message.data.content_type 字段"""

    TEXT = 2
    LOCATION = 6
    LINK = 13
    VOICE = 16
    REDPACKET = 26
    GIF = 29
    CARD = 41
    MINIPROGRAM = 78
    IMAGE = 101
    FILE = 102
    VIDEO = 103
    IMAGE_TEXT = 123
    VIDEO_CHANNEL = 141
    VIDEO_CHANNEL_LIVE = 146


# ---- 映射表：事件类型 → ERP 消息类型 ----
EVENT_TYPE_TO_MESSAGE_TYPE: dict[int, str] = {
    EventType.TEXT_MESSAGE: "text",
    EventType.IMAGE_MESSAGE: "image",
    EventType.VIDEO_MESSAGE: "video",
    EventType.VOICE_MESSAGE: "voice",
    EventType.FILE_MESSAGE: "file",
    EventType.LOCATION_MESSAGE: "location",
    EventType.LINK_MESSAGE: "link",
    EventType.GIF_MESSAGE: "gif",
    EventType.REDPACKET_MESSAGE: "redpacket",
    EventType.CARD_MESSAGE: "card",
    EventType.MINIPROGRAM_MESSAGE: "miniprogram",
    EventType.IMAGE_TEXT_MESSAGE: "text",
    EventType.REVOKE_MESSAGE: "revoke",
    EventType.VIDEO_CHANNEL_MESSAGE: "video_channel",
    EventType.VIDEO_CHANNEL_LIVE_MESSAGE: "video_channel_live",
    EventType.FRIEND_REQUEST: "friend_request",
    EventType.FRIEND_ADD: "friend_add",
    EventType.FRIEND_DELETE: "friend_delete",
    EventType.GROUP_MEMBER_ADD: "group_member_add",
    EventType.GROUP_MEMBER_DELETE: "group_member_delete",
    EventType.GROUP_CREATE: "group_create",
    EventType.GROUP_QUIT: "group_quit",
    EventType.GROUP_NAME_CHANGE: "group_name_change",
}

# ---- 映射表：内容类型 → ERP 消息类型 ----
CONTENT_TYPE_TO_MESSAGE_TYPE: dict[int, str] = {
    WxType.TEXT: "text",
    WxType.LOCATION: "location",
    WxType.LINK: "link",
    WxType.VOICE: "voice",
    WxType.REDPACKET: "redpacket",
    WxType.GIF: "gif",
    WxType.CARD: "card",
    WxType.MINIPROGRAM: "miniprogram",
    WxType.IMAGE: "image",
    WxType.FILE: "file",
    WxType.VIDEO: "video",
    WxType.IMAGE_TEXT: "text",
    WxType.VIDEO_CHANNEL: "video_channel",
    WxType.VIDEO_CHANNEL_LIVE: "video_channel_live",
}

# 对订单处理有意义的消息事件类型
ORDER_RELEVANT_EVENT_TYPES: set[int] = {
    EventType.TEXT_MESSAGE,
    EventType.IMAGE_MESSAGE,
    EventType.FILE_MESSAGE,
    EventType.IMAGE_TEXT_MESSAGE,
}

# 系统事件（非用户消息，用于日志但不参与订单处理）
SYSTEM_EVENT_TYPES: set[int] = {
    EventType.API_READY,
    EventType.LOGIN_QRCODE,
    EventType.LOGIN_QRCODE_STATUS,
    EventType.LOGIN_SUCCESS,
    EventType.LOGIN_SUCCESS_WITH_CORP,
    EventType.LOGOUT,
    EventType.REVOKE_MESSAGE,
    EventType.FRIEND_REQUEST,
    EventType.FRIEND_ADD,
    EventType.FRIEND_DELETE,
    EventType.GROUP_MEMBER_ADD,
    EventType.GROUP_MEMBER_DELETE,
    EventType.GROUP_CREATE,
    EventType.GROUP_QUIT,
    EventType.GROUP_NAME_CHANGE,
}
