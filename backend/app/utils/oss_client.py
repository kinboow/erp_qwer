import io
import logging
from datetime import timedelta

from minio import Minio
from minio.error import S3Error

from app.config import settings

logger = logging.getLogger(__name__)


class OSSClient:
    """MinIO / S3 兼容的对象存储客户端"""

    def __init__(self):
        self.endpoint = settings.OSS_ENDPOINT
        self.bucket_name = settings.OSS_BUCKET_NAME
        self.use_ssl = settings.OSS_USE_SSL
        self.client = Minio(
            self.endpoint,
            access_key=settings.OSS_ACCESS_KEY_ID,
            secret_key=settings.OSS_ACCESS_KEY_SECRET,
            secure=self.use_ssl,
        )
        self._ensure_bucket()

    def _ensure_bucket(self):
        """自动创建 bucket（如果不存在）"""
        try:
            if not self.client.bucket_exists(self.bucket_name):
                self.client.make_bucket(self.bucket_name)
                logger.info("[MinIO] 已创建 bucket: %s", self.bucket_name)
        except Exception as e:
            logger.warning("[MinIO] 检查/创建 bucket 失败: %s", e)

    def upload_file(self, object_name: str, file_data: bytes, content_type: str = "application/octet-stream") -> str:
        """上传文件，返回可访问的 URL"""
        try:
            self.client.put_object(
                self.bucket_name,
                object_name,
                io.BytesIO(file_data),
                length=len(file_data),
                content_type=content_type,
            )
            scheme = "https" if self.use_ssl else "http"
            return f"{scheme}://{self.endpoint}/{self.bucket_name}/{object_name}"
        except S3Error as e:
            raise Exception(f"文件上传失败: {str(e)}")

    def delete_file(self, object_name: str) -> bool:
        """删除文件"""
        try:
            self.client.remove_object(self.bucket_name, object_name)
            return True
        except S3Error as e:
            raise Exception(f"文件删除失败: {str(e)}")

    def get_file_url(self, object_name: str, expires: int = 3600) -> str:
        """获取文件预签名访问 URL"""
        try:
            url = self.client.presigned_get_object(
                self.bucket_name,
                object_name,
                expires=timedelta(seconds=expires),
            )
            return url
        except S3Error as e:
            raise Exception(f"获取文件URL失败: {str(e)}")


oss_client = OSSClient()
