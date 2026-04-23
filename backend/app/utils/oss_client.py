import oss2
from app.config import settings


class OSSClient:
    def __init__(self):
        auth = oss2.Auth(settings.OSS_ACCESS_KEY_ID, settings.OSS_ACCESS_KEY_SECRET)
        self.bucket = oss2.Bucket(auth, settings.OSS_ENDPOINT, settings.OSS_BUCKET_NAME)

    def upload_file(self, object_name: str, file_data: bytes) -> str:
        """上传文件"""
        try:
            result = self.bucket.put_object(object_name, file_data)
            if result.status == 200:
                return f"https://{settings.OSS_BUCKET_NAME}.{settings.OSS_ENDPOINT}/{object_name}"
            return None
        except Exception as e:
            raise Exception(f"文件上传失败: {str(e)}")

    def delete_file(self, object_name: str) -> bool:
        """删除文件"""
        try:
            result = self.bucket.delete_object(object_name)
            return result.status == 204
        except Exception as e:
            raise Exception(f"文件删除失败: {str(e)}")

    def get_file_url(self, object_name: str, expires: int = 3600) -> str:
        """获取文件访问URL"""
        try:
            url = self.bucket.sign_url('GET', object_name, expires)
            return url
        except Exception as e:
            raise Exception(f"获取文件URL失败: {str(e)}")


oss_client = OSSClient()
