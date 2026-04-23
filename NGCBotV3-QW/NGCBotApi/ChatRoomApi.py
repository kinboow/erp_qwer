from .InterFaceApi import sendPost
from loguru import logger

class ChatRoomApi:
    def __init__(self):
        pass

    async def getRooms(self, robotId: str, pageNum: int = 1, pageSize: int = 100):
        """
        获取群列表
        API: POST /api/{wxid}/rooms/get

        Args:
            robotId (str): 机器人的微信ID
            pageNum (int): 页码，默认1
            pageSize (int): 每页数量，默认100

        Returns:
            dict: {'code': 0, 'msg': 'ok', 'data': {'total': 20, 'rooms': [...]}}
        """
        try:
            data = {
                'page_num': pageNum,
                'page_size': pageSize
            }
            jsonData = await sendPost(data=data, robotId=robotId, route='rooms/get')
            return jsonData
        except Exception as e:
            logger.error(f'获取群列表出现错误: {e}')
            return {'code': -1, 'msg': f'获取群列表出现错误: {e}', 'data': {}}

    async def getRoomMembers(self, robotId: str, conversationId: str, pageNum: int = 1, pageSize: int = 100):
        """
        获取群成员列表
        API: POST /api/{wxid}/rooms/members

        Args:
            robotId (str): 机器人的微信ID
            conversationId (str): 群的conversation_id
            pageNum (int): 页码，默认1
            pageSize (int): 每页数量，默认100

        Returns:
            dict: {'code': 0, 'msg': 'ok', 'data': {...}}
        """
        try:
            data = {
                'conversation_id': conversationId,
                'page_num': pageNum,
                'page_size': pageSize
            }
            jsonData = await sendPost(data=data, robotId=robotId, route='rooms/members')
            return jsonData
        except Exception as e:
            logger.error(f'获取群成员列表出现错误: {e}')
            return {'code': -1, 'msg': f'获取群成员列表出现错误: {e}', 'data': {}}

    async def createRoom(self, robotId: str, userList: list):
        """
        创建群
        API: POST /api/{wxid}/rooms/create

        Args:
            robotId (str): 机器人的微信ID
            userList (list): 用户ID列表

        Returns:
            dict: {'code': 0, 'msg': 'ok', 'data': {}}
        """
        try:
            data = {
                'user_list': userList
            }
            jsonData = await sendPost(data=data, robotId=robotId, route='rooms/create')
            return jsonData
        except Exception as e:
            logger.error(f'创建群出现错误: {e}')
            return {'code': -1, 'msg': f'创建群出现错误: {e}', 'data': {}}

    async def modifyRoomName(self, robotId: str, conversationId: str, name: str):
        """
        修改群名
        API: POST /api/{wxid}/rooms/modify_name

        Args:
            robotId (str): 机器人的微信ID
            conversationId (str): 群的conversation_id
            name (str): 新的群名称

        Returns:
            dict: {'code': 0, 'msg': 'ok', 'data': {}}
        """
        try:
            data = {
                'conversation_id': conversationId,
                'name': name
            }
            jsonData = await sendPost(data=data, robotId=robotId, route='rooms/modify_name')
            return jsonData
        except Exception as e:
            logger.error(f'修改群名出现错误: {e}')
            return {'code': -1, 'msg': f'修改群名出现错误: {e}', 'data': {}}

    async def inviteRoomMember(self, robotId: str, conversationId: str, userList: list):
        """
        邀请入群
        API: POST /api/{wxid}/rooms/invite

        Args:
            robotId (str): 机器人的微信ID
            conversationId (str): 群的conversation_id
            userList (list): 用户ID列表

        Returns:
            dict: {'code': 0, 'msg': 'ok', 'data': {}}
        """
        try:
            data = {
                'conversation_id': conversationId,
                'user_list': userList
            }
            jsonData = await sendPost(data=data, robotId=robotId, route='rooms/invite')
            return jsonData
        except Exception as e:
            logger.error(f'邀请入群出现错误: {e}')
            return {'code': -1, 'msg': f'邀请入群出现错误: {e}', 'data': {}}

    async def delRoomMember(self, robotId: str, conversationId: str, userList: list):
        """
        踢群成员
        API: POST /api/{wxid}/rooms/del_member

        Args:
            robotId (str): 机器人的微信ID
            conversationId (str): 群的conversation_id
            userList (list): 用户ID列表

        Returns:
            dict: {'code': 0, 'msg': 'ok', 'data': {}}
        """
        try:
            data = {
                'conversation_id': conversationId,
                'user_list': userList
            }
            jsonData = await sendPost(data=data, robotId=robotId, route='rooms/del_member')
            return jsonData
        except Exception as e:
            logger.error(f'踢群成员出现错误: {e}')
            return {'code': -1, 'msg': f'踢群成员出现错误: {e}', 'data': {}}

    async def addMemberAsContact(self, robotId: str, roomConversationId: str, userId: str, corpId: str, verify: str = ''):
        """
        添加群成员为好友
        API: POST /api/{wxid}/rooms/add_member_as_contact

        Args:
            robotId (str): 机器人的微信ID
            roomConversationId (str): 群的room_conversation_id
            userId (str): 用户ID
            corpId (str): 企业ID
            verify (str): 验证消息，默认为空

        Returns:
            dict: {'code': 0, 'msg': 'ok', 'data': {}}
        """
        try:
            data = {
                'room_conversation_id': roomConversationId,
                'user_id': userId,
                'corp_id': corpId,
                'verify': verify
            }
            jsonData = await sendPost(data=data, robotId=robotId, route='rooms/add_member_as_contact')
            return jsonData
        except Exception as e:
            logger.error(f'添加群成员为好友出现错误: {e}')
            return {'code': -1, 'msg': f'添加群成员为好友出现错误: {e}', 'data': {}}

    async def modifyRoomNotice(self, robotId: str, roomConversationId: str, notice: str):
        """
        发布群公告
        API: POST /api/{wxid}/rooms/modify_notice

        Args:
            robotId (str): 机器人的微信ID
            roomConversationId (str): 群的room_conversation_id
            notice (str): 公告内容

        Returns:
            dict: {'code': 0, 'msg': 'ok', 'data': {}}
        """
        try:
            data = {
                'room_conversation_id': roomConversationId,
                'notice': notice
            }
            jsonData = await sendPost(data=data, robotId=robotId, route='rooms/modify_notice')
            return jsonData
        except Exception as e:
            logger.error(f'发布群公告出现错误: {e}')
            return {'code': -1, 'msg': f'发布群公告出现错误: {e}', 'data': {}}

    async def quitRoom(self, robotId: str, conversationId: str):
        """
        退出群聊
        API: POST /api/{wxid}/rooms/quit

        Args:
            robotId (str): 机器人的微信ID
            conversationId (str): 群的conversation_id

        Returns:
            dict: {'code': 0, 'msg': 'ok', 'data': {}}
        """
        try:
            data = {
                'room_conversation_id': conversationId
            }
            jsonData = await sendPost(data=data, robotId=robotId, route='rooms/quit')
            return jsonData
        except Exception as e:
            logger.error(f'退出群聊出现错误: {e}')
            return {'code': -1, 'msg': f'退出群聊出现错误: {e}', 'data': {}}

    async def dismissRoom(self, robotId: str, conversationId: str):
        """
        解散群
        API: POST /api/{wxid}/rooms/dismiss

        Args:
            robotId (str): 机器人的微信ID
            conversationId (str): 群的conversation_id

        Returns:
            dict: {'code': 0, 'msg': 'ok', 'data': {}}
        """
        try:
            data = {
                'room_conversation_id': conversationId
            }
            jsonData = await sendPost(data=data, robotId=robotId, route='rooms/dismiss')
            return jsonData
        except Exception as e:
            logger.error(f'解散群出现错误: {e}')
            return {'code': -1, 'msg': f'解散群出现错误: {e}', 'data': {}}

