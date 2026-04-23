from .BotApi import BotApi
from .CdnMsgApi import CdnMsgApi
from .ChatRoomApi import ChatRoomApi
from .FriendApi import FriendApi
from .SendMsgApi import SendMsgApi


class NGCBotApi(SendMsgApi, BotApi, FriendApi, ChatRoomApi, CdnMsgApi):
    """
    NGCBot API 主类
    
    包含模块:
    - BotApi: 登录相关接口
    - SendMsgApi: 消息发送接口
    - FriendApi: 联系人管理接口
    - ChatRoomApi: 群管理接口
    - CdnMsgApi: CDN相关接口
    """
    def __init__(self):
        super().__init__()
