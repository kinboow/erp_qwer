from .InterFaceApi import sendPost
from loguru import logger

class CdnMsgApi:
    def __init__(self):
        pass

    async def cdnUpload(self, robotId: str, filePath: str, fileType: int):
        """
        C2C CDN上传
        API: POST /api/{wxid}/cdn/c2c_upload

        Args:
            robotId (str): 机器人的微信ID
            filePath (str): 文件路径
            fileType (int): 文件类型

        Returns:
            dict: {'code': 0, 'msg': 'ok', 'data': {...}}
        """
        try:
            data = {
                'file_path': filePath,
                'file_type': fileType
            }
            jsonData = await sendPost(data=data, robotId=robotId, route='cdn/c2c_upload')
            return jsonData
        except Exception as e:
            logger.error(f'CDN上传出现错误: {e}')
            return {'code': -1, 'msg': f'CDN上传出现错误: {e}', 'data': {}}

    async def cdnDownload(self, robotId: str, aesKey: str, fileId: str, savePath: str, fileSize: int, fileType: int):
        """
        C2C CDN下载
        API: POST /api/{wxid}/cdn/c2c_download

        Args:
            robotId (str): 机器人的微信ID
            aesKey (str): AES密钥
            fileId (str): 文件ID
            savePath (str): 保存路径
            fileSize (int): 文件大小
            fileType (int): 文件类型

        Returns:
            dict: {'code': 0, 'msg': 'ok', 'data': {}}
        """
        try:
            data = {
                'aes_key': aesKey,
                'file_id': fileId,
                'save_path': savePath,
                'file_size': fileSize,
                'file_type': fileType
            }
            jsonData = await sendPost(data=data, robotId=robotId, route='cdn/c2c_download')
            return jsonData
        except Exception as e:
            logger.error(f'CDN下载出现错误: {e}')
            return {'code': -1, 'msg': f'CDN下载出现错误: {e}', 'data': {}}

    async def cdnDownloadWecom(self, robotId: str, url: str, authKey: str, aesKey: str, size: int, savePath: str):
        """
        WX CDN下载（企业微信）
        API: POST /api/{wxid}/cdn/wx_download

        Args:
            robotId (str): 机器人的微信ID
            url (str): CDN URL
            authKey (str): 认证密钥
            aesKey (str): AES密钥
            size (int): 文件大小
            savePath (str): 保存路径

        Returns:
            dict: {'code': 0, 'msg': 'ok', 'data': {}}
        """
        try:
            data = {
                'url': url,
                'auth_key': authKey,
                'aes_key': aesKey,
                'size': size,
                'save_path': savePath
            }
            jsonData = await sendPost(data=data, robotId=robotId, route='cdn/wx_download')
            return jsonData
        except Exception as e:
            logger.error(f'企业微信CDN下载出现错误: {e}')
            return {'code': -1, 'msg': f'企业微信CDN下载出现错误: {e}', 'data': {}}
