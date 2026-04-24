import io
import json
import logging
from datetime import timedelta

from minio import Minio
from minio.error import S3Error

from app.config import settings

logger = logging.getLogger(__name__)


class OSSClient:
    """MinIO / S3 兼容的对象存储客户端（懒初始化，首次使用时连接）"""

    def __init__(self):
        self._client = None
        self._bucket_ready = False

    def _get_client(self) -> Minio:
        if self._client is None:
            self._client = Minio(
                settings.OSS_ENDPOINT,
                access_key=settings.OSS_ACCESS_KEY_ID,
                secret_key=settings.OSS_ACCESS_KEY_SECRET,
                secure=settings.OSS_USE_SSL,
            )
        if not self._bucket_ready:
            self._ensure_bucket()
            self._bucket_ready = True
        return self._client

    @property
    def endpoint(self) -> str:
        return settings.OSS_ENDPOINT

    @property
    def bucket_name(self) -> str:
        return settings.OSS_BUCKET_NAME

    @property
    def use_ssl(self) -> bool:
        return settings.OSS_USE_SSL

    @property
    def client(self) -> Minio:
        return self._get_client()

    def _ensure_bucket(self):
        """自动创建 bucket（保持私有，不设置公开读）"""
        try:
            if not self._client.bucket_exists(self.bucket_name):
                self._client.make_bucket(self.bucket_name)
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

    def download_file(self, object_name: str) -> bytes:
        """从 MinIO 下载文件，返回字节内容"""
        response = None
        try:
            response = self.client.get_object(self.bucket_name, object_name)
            return response.read()
        except S3Error as e:
            raise Exception(f"文件下载失败: {str(e)}")
        finally:
            if response:
                response.close()
                response.release_conn()

    def parse_object_name(self, url: str) -> str | None:
        """从 MinIO URL 中解析出 object_name，如 erp/qr/xxx.jpg"""
        prefix = f"/{self.bucket_name}/"
        idx = url.find(prefix)
        if idx >= 0:
            return url[idx + len(prefix):].split("?")[0]
        return None

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
