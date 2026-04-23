# -*- coding: utf-8 -*-

class EventType:
    """企业微信消息通知类型常量 - 基于接口文档 message.type"""
    
    # ============ 系统通知 ============
    # 接口就绪通知
    API_READY = 11024
    
    # 登录二维码通知
    LOGIN_QRCODE = 11028
    
    # 登录二维码状态通知
    LOGIN_QRCODE_STATUS = 11174
    
    # 用户登录成功通知(无公司名称)
    LOGIN_SUCCESS = 11026
    
    # 用户登录成功通知(含公司名称)
    LOGIN_SUCCESS_WITH_CORP = 11179
    
    # 用户退出通知
    LOGOUT = 11027
    
    
    # ============ 消息通知 ============
    # 文本消息通知
    TEXT_MESSAGE = 11041
    
    # 图片消息通知
    IMAGE_MESSAGE = 11042
    
    # 链接消息通知
    LINK_MESSAGE = 11047
    
    # GIF消息通知
    GIF_MESSAGE = 11048
    
    # 文件消息通知
    FILE_MESSAGE = 11045
    
    # 视频消息通知
    VIDEO_MESSAGE = 11043
    
    # 名片消息通知
    CARD_MESSAGE = 11050
    
    # 小程序消息通知
    MINIPROGRAM_MESSAGE = 11066
    
    # 视频号消息通知
    VIDEO_CHANNEL_MESSAGE = 11124
    
    # 视频号直播消息通知
    VIDEO_CHANNEL_LIVE_MESSAGE = 11195
    
    # 红包消息通知
    REDPACKET_MESSAGE = 11049
    
    # 语音消息通知
    VOICE_MESSAGE = 11044
    
    # 位置消息通知
    LOCATION_MESSAGE = 11046
    
    # 图文消息通知
    IMAGE_TEXT_MESSAGE = 11068
    
    # 撤回消息通知
    REVOKE_MESSAGE = 11123
    
    
    # ============ 好友事件通知 ============
    # 好友申请通知
    FRIEND_REQUEST = 11063
    
    # 好友新增通知
    FRIEND_ADD = 11076
    
    # 好友删除通知
    FRIEND_DELETE = 11077
    
    
    # ============ 群聊事件通知 ============
    # 新增群通知
    GROUP_CREATE = 11074
    
    # 群成员增加通知
    GROUP_MEMBER_ADD = 11072
    
    # 群成员减少通知
    GROUP_MEMBER_DELETE = 11073
    
    # 主动退群通知
    GROUP_QUIT = 11075
    
    # 群名称变化通知
    GROUP_NAME_CHANGE = 11078


class WxType:
    """消息内容类型常量 - 基于 message.data.content_type"""
    
    # 文本类型
    TEXT = 2
    
    # 位置类型
    LOCATION = 6
    
    # 链接类型
    LINK = 13
    
    # 语音类型
    VOICE = 16
    
    # 红包类型
    REDPACKET = 26
    
    # GIF表情类型
    GIF = 29
    
    # 名片类型
    CARD = 41
    
    # 小程序类型
    MINIPROGRAM = 78
    
    # 图片类型
    IMAGE = 101
    
    # 文件类型
    FILE = 102
    
    # 视频类型
    VIDEO = 103
    
    # 图文类型
    IMAGE_TEXT = 123
    
    # 视频号类型
    VIDEO_CHANNEL = 141
    
    # 视频号直播类型
    VIDEO_CHANNEL_LIVE = 146


# 向后兼容别名

