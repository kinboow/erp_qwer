from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # 数据库配置
    DB_HOST: str = "localhost"
    DB_PORT: int = 3306
    DB_USER: str = "root"
    DB_PASSWORD: str = ""
    DB_NAME: str = "factory_management"

    # Redis配置
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_PASSWORD: str = ""
    REDIS_DB: int = 0

    # JWT配置
    JWT_SECRET_KEY: str = "your_jwt_secret_key"
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 10080

    # 服务器配置
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8900
    DEBUG: bool = True

    # MinIO / OSS 配置
    OSS_ENDPOINT: str = "localhost:9002"
    OSS_ACCESS_KEY_ID: str = "minioadmin"
    OSS_ACCESS_KEY_SECRET: str = "minioadmin123"
    OSS_BUCKET_NAME: str = "erp"
    OSS_USE_SSL: bool = False

    # 消息队列配置
    MQ_HOST: str = "localhost"
    MQ_PORT: int = 5672
    MQ_USER: str = "guest"
    MQ_PASSWORD: str = "guest"
    MQ_VHOST: str = "/"

    # AI解析配置（通义千问）
    OPENAI_BASE_URL: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    OPENAI_API_KEY: str = ""
    OPENAI_MODEL: str = "qwen3.5-flash"
    OPENAI_VISION_MODEL: str = "qwen3.5-flash"

    WECHAT_QR_DETECT_PROTO_PATH: str = ""
    WECHAT_QR_DETECT_MODEL_PATH: str = ""
    WECHAT_QR_SUPER_RES_PROTO_PATH: str = ""
    WECHAT_QR_SUPER_RES_MODEL_PATH: str = ""

    # ERP集成配置
    ERP_BASE_URL: str = ""
    ERP_USERNAME: str = ""
    ERP_PASSWORD: str = ""
    ERP_QR_IMAGE_PATH: str = ""
    ERP_DEFAULT_SALESPERSON: str = ""
    ERP_DEFAULT_CUSTOMER_TYPE: str = ""
    ERP_DEFAULT_CURRENCY: str = "人民币"
    ERP_DEFAULT_BRAND: str = ""
    ERP_DEFAULT_SHIPPING_METHOD: str = ""

    # ERP 同步配置
    ERP_SYNC_INTERVAL_MINUTES: int = 15
    ERP_SYNC_DAYS_BACK: int = 360

    @property
    def DATABASE_URL(self) -> str:
        return f"mysql+pymysql://{self.DB_USER}:{self.DB_PASSWORD}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}?charset=utf8mb4"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8-sig"
        case_sensitive = True
        extra = "ignore"


@lru_cache()
def get_settings() -> Settings:
    """获取配置实例（单例模式）"""
    return Settings()


settings = get_settings()
