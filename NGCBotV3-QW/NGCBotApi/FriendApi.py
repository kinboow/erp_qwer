from .InterFaceApi import sendPost
from loguru import logger

class FriendApi:
    def __init__(self):
        pass

    async def getInternalContacts(self, robotId: str, pageNum: int = 1, pageSize: int = 100):
        """
        获取内部联系人列表
        API: POST /api/{wxid}/contacts/internal

        Args:
            robotId (str): 机器人的微信ID
            pageNum (int): 页码，默认1
            pageSize (int): 每页数量，默认100

        Returns:
            dict: {'code': 0, 'msg': 'ok', 'data': {'total': 150, 'contacts': [...]}}
        """
        try:
            data = {
                'page_num': pageNum,
                'page_size': pageSize
            }
            jsonData = await sendPost(data=data, robotId=robotId, route='contacts/internal')
            return jsonData
        except Exception as e:
            logger.error(f'获取内部联系人列表出现错误: {e}')
            return {'code': -1, 'msg': f'获取内部联系人列表出现错误: {e}', 'data': {}}

    async def getExternalContacts(self, robotId: str, pageNum: int = 1, pageSize: int = 100):
        """
        获取外部联系人列表
        API: POST /api/{wxid}/contacts/external

        Args:
            robotId (str): 机器人的微信ID
            pageNum (int): 页码，默认1
            pageSize (int): 每页数量，默认100

        Returns:
            dict: {'code': 0, 'msg': 'ok', 'data': {'total': 150, 'contacts': [...]}}
        """
        try:
            data = {
                'page_num': pageNum,
                'page_size': pageSize
            }
            jsonData = await sendPost(data=data, robotId=robotId, route='contacts/external')
            return jsonData
        except Exception as e:
            logger.error(f'获取外部联系人列表出现错误: {e}')
            return {'code': -1, 'msg': f'获取外部联系人列表出现错误: {e}', 'data': {}}

    async def getContactInfo(self, robotId: str, userId: str):
        """
        获取联系人信息
        API: POST /api/{wxid}/contacts/info

        Args:
            robotId (str): 机器人的微信ID
            userId (str): 用户ID

        Returns:
            dict: {'code': 0, 'msg': 'ok', 'data': {...}}
        """
        try:
            data = {
                'user_id': userId
            }
            jsonData = await sendPost(data=data, robotId=robotId, route='contacts/info')
            return jsonData
        except Exception as e:
            logger.error(f'获取联系人信息出现错误: {e}')
            return {'code': -1, 'msg': f'获取联系人信息出现错误: {e}', 'data': {}}

    async def searchContact(self, robotId: str, keyword: str):
        """
        搜索用户
        API: POST /api/{wxid}/contacts/search

        Args:
            robotId (str): 机器人的微信ID
            keyword (str): 搜索关键词（手机号、微信号等）

        Returns:
            dict: {'code': 0, 'msg': 'ok', 'data': {...}}
        """
        try:
            data = {
                'keyword': keyword
            }
            jsonData = await sendPost(data=data, robotId=robotId, route='contacts/search')
            return jsonData
        except Exception as e:
            logger.error(f'搜索用户出现错误: {e}')
            return {'code': -1, 'msg': f'搜索用户出现错误: {e}', 'data': {}}

    async def modifyRemark(self, robotId: str, userId: str, remark: str):
        """
        修改好友备注
        API: POST /api/{wxid}/contacts/modify_remark

        Args:
            robotId (str): 机器人的微信ID
            userId (str): 用户ID
            remark (str): 新备注

        Returns:
            dict: {'code': 0, 'msg': 'ok', 'data': {}}
        """
        try:
            data = {
                'user_id': userId,
                'remark': remark
            }
            jsonData = await sendPost(data=data, robotId=robotId, route='contacts/modify_remark')
            return jsonData
        except Exception as e:
            logger.error(f'修改好友备注出现错误: {e}')
            return {'code': -1, 'msg': f'修改好友备注出现错误: {e}', 'data': {}}

    async def deleteContact(self, robotId: str, userId: str, corpId: str):
        """
        删除联系人
        API: POST /api/{wxid}/contacts/delete

        Args:
            robotId (str): 机器人的微信ID
            userId (str): 用户ID
            corpId (str): 企业ID

        Returns:
            dict: {'code': 0, 'msg': 'ok', 'data': {}}
        """
        try:
            data = {
                'user_id': userId,
                'corp_id': corpId
            }
            jsonData = await sendPost(data=data, robotId=robotId, route='contacts/delete')
            return jsonData
        except Exception as e:
            logger.error(f'删除联系人出现错误: {e}')
            return {'code': -1, 'msg': f'删除联系人出现错误: {e}', 'data': {}}

    async def addWxUser(self, robotId: str, userId: str, openid: str, wxTicket: str, verify: str = ''):
        """
        添加微信用户
        API: POST /api/{wxid}/contacts/add_wx_user

        Args:
            robotId (str): 机器人的微信ID
            userId (str): 用户ID
            openid (str): OpenID
            wxTicket (str): 微信ticket
            verify (str): 验证消息，默认为空

        Returns:
            dict: {'code': 0, 'msg': 'ok', 'data': {}}
        """
        try:
            data = {
                'user_id': userId,
                'openid': openid,
                'wx_ticket': wxTicket,
                'verify': verify
            }
            jsonData = await sendPost(data=data, robotId=robotId, route='contacts/add_wx_user')
            return jsonData
        except Exception as e:
            logger.error(f'添加微信用户出现错误: {e}')
            return {'code': -1, 'msg': f'添加微信用户出现错误: {e}', 'data': {}}

    async def addWxworkUser(self, robotId: str, userId: str, corpId: str, ticket: str, verify: str = ''):
        """
        添加企微用户
        API: POST /api/{wxid}/contacts/add_wxwork_user

        Args:
            robotId (str): 机器人的微信ID
            userId (str): 用户ID
            corpId (str): 企业ID
            ticket (str): ticket
            verify (str): 验证消息，默认为空

        Returns:
            dict: {'code': 0, 'msg': 'ok', 'data': {}}
        """
        try:
            data = {
                'user_id': userId,
                'corp_id': corpId,
                'ticket': ticket,
                'verify': verify
            }
            jsonData = await sendPost(data=data, robotId=robotId, route='contacts/add_wxwork_user')
            return jsonData
        except Exception as e:
            logger.error(f'添加企微用户出现错误: {e}')
            return {'code': -1, 'msg': f'添加企微用户出现错误: {e}', 'data': {}}

    async def addCard(self, robotId: str, userId: str, corpId: str, fromUserId: str, verify: str = ''):
        """
        添加名片
        API: POST /api/{wxid}/contacts/add_card

        Args:
            robotId (str): 机器人的微信ID
            userId (str): 用户ID
            corpId (str): 企业ID
            fromUserId (str): 来源用户ID
            verify (str): 验证消息，默认为空

        Returns:
            dict: {'code': 0, 'msg': 'ok', 'data': {}}
        """
        try:
            data = {
                'user_id': userId,
                'corp_id': corpId,
                'from_user_id': fromUserId,
                'verify': verify
            }
            jsonData = await sendPost(data=data, robotId=robotId, route='contacts/add_card')
            return jsonData
        except Exception as e:
            logger.error(f'添加名片出现错误: {e}')
            return {'code': -1, 'msg': f'添加名片出现错误: {e}', 'data': {}}

    async def addDeleted(self, robotId: str, userId: str, corpId: str, verify: str = ''):
        """
        添加删除的联系人
        API: POST /api/{wxid}/contacts/add_deleted

        Args:
            robotId (str): 机器人的微信ID
            userId (str): 用户ID
            corpId (str): 企业ID
            verify (str): 验证消息，默认为空

        Returns:
            dict: {'code': 0, 'msg': 'ok', 'data': {}}
        """
        try:
            data = {
                'user_id': userId,
                'corp_id': corpId,
                'verify': verify
            }
            jsonData = await sendPost(data=data, robotId=robotId, route='contacts/add_deleted')
            return jsonData
        except Exception as e:
            logger.error(f'添加删除的联系人出现错误: {e}')
            return {'code': -1, 'msg': f'添加删除的联系人出现错误: {e}', 'data': {}}

    async def modifyDesc(self, robotId: str, userId: str, desc: str):
        """
        修改描述
        API: POST /api/{wxid}/contacts/modify_desc

        Args:
            robotId (str): 机器人的微信ID
            userId (str): 用户ID
            desc (str): 描述

        Returns:
            dict: {'code': 0, 'msg': 'ok', 'data': {}}
        """
        try:
            data = {
                'user_id': userId,
                'desc': desc
            }
            jsonData = await sendPost(data=data, robotId=robotId, route='contacts/modify_desc')
            return jsonData
        except Exception as e:
            logger.error(f'修改描述出现错误: {e}')
            return {'code': -1, 'msg': f'修改描述出现错误: {e}', 'data': {}}

    async def modifyPhone(self, robotId: str, userId: str, phoneList: list):
        """
        修改手机号
        API: POST /api/{wxid}/contacts/modify_phone

        Args:
            robotId (str): 机器人的微信ID
            userId (str): 用户ID
            phoneList (list): 手机号列表

        Returns:
            dict: {'code': 0, 'msg': 'ok', 'data': {}}
        """
        try:
            data = {
                'user_id': userId,
                'phone_list': phoneList
            }
            jsonData = await sendPost(data=data, robotId=robotId, route='contacts/modify_phone')
            return jsonData
        except Exception as e:
            logger.error(f'修改手机号出现错误: {e}')
            return {'code': -1, 'msg': f'修改手机号出现错误: {e}', 'data': {}}

    async def acceptRequest(self, robotId: str, userId: str, corpId: str):
        """
        接受好友申请
        API: POST /api/{wxid}/contacts/accept_request

        Args:
            robotId (str): 机器人的微信ID
            userId (str): 用户ID
            corpId (str): 企业ID

        Returns:
            dict: {'code': 0, 'msg': 'ok', 'data': {}}
        """
        try:
            data = {
                'user_id': userId,
                'corp_id': corpId
            }
            jsonData = await sendPost(data=data, robotId=robotId, route='contacts/accept_request')
            return jsonData
        except Exception as e:
            logger.error(f'接受好友申请出现错误: {e}')
            return {'code': -1, 'msg': f'接受好友申请出现错误: {e}', 'data': {}}

