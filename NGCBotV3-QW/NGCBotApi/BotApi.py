from .InterFaceApi import sendPost
from loguru import logger

class BotApi:
    def __init__(self):
        pass

    async def getLoginInfo(self, robotId: str):
        """
        获取登录账号信息
        API: POST /api/{wxid}/self/info

        Args:
            robotId (str): 机器人的微信ID

        Returns:
            dict: {'code': 0, 'msg': 'ok', 'data': {'wxid': '', 'nickname': '', 'avatar': '', 'phone': ''}}
        """
        try:
            data = {}
            jsonData = await sendPost(data, robotId=robotId, route='self/info')
            return jsonData
        except Exception as e:
            logger.error(f'获取登录信息出现错误, 错误信息: {e}')
            return {'code': -1, 'msg': f'获取登录信息出现错误: {e}', 'data': {}}

    async def getBotInfo(self, robotId: str):
        """
        获取个人信息（同getLoginInfo）
        API: POST /api/{wxid}/self/info

        Args:
            robotId (str): 机器人的微信ID

        Returns:
            dict: 同getLoginInfo
        """
        # 新API中getLoginInfo和getBotInfo是同一个接口
        return await self.getLoginInfo(robotId)

    async def refershQrcode(self, robotId: str):
        """
        刷新登录二维码
        API: POST /api/{wxid}/refresh_qrcode

        Args:
            robotId (str): 机器人的微信ID

        Returns:
            dict: {'code': 0, 'msg': 'ok', 'data': {}}
        """
        try:
            data = {}
            jsonData = await sendPost(data, robotId=robotId, route='refresh_qrcode')
            return jsonData
        except Exception as e:
            logger.error(f'刷新二维码出现错误, 错误信息: {e}')
            return {'code': -1, 'msg': f'刷新二维码出现错误: {e}', 'data': {}}

    async def logout(self, robotId: str):
        """
        退出登录
        API: POST /api/{wxid}/logout

        Args:
            robotId (str): 机器人的微信ID

        Returns:
            dict: {'code': 0, 'msg': 'ok', 'data': {}}
        """
        try:
            data = {}
            jsonData = await sendPost(data, robotId=robotId, route='logout')
            return jsonData
        except Exception as e:
            logger.error(f'退出登录出现错误, 错误信息: {e}')
            return {'code': -1, 'msg': f'退出登录出现错误: {e}', 'data': {}}

    async def getSelfQrcode(self, robotId: str):
        """
        获取自己的二维码
        API: POST /api/{wxid}/self/qrcode

        Args:
            robotId (str): 机器人的微信ID

        Returns:
            dict: {'code': 0, 'msg': 'ok', 'data': {}}
        """
        try:
            data = {}
            jsonData = await sendPost(data, robotId=robotId, route='self/qrcode')
            return jsonData
        except Exception as e:
            logger.error(f'获取二维码出现错误, 错误信息: {e}')
            return {'code': -1, 'msg': f'获取二维码出现错误: {e}', 'data': {}}




if __name__ == '__main__':
    import asyncio

    botApi = BotApi()
    result = asyncio.run(BotApi().getLoginInfo(robotId='1688855118748144'))
    #result = asyncio.run(BotApi().getBotInfo(robotId='1688855118748144'))
    #result = asyncio.run(BotApi().refershQrcode(robotId='1688855118748144'))
    print(result)

