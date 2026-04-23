from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Project root: app/config.py → app/ → project root
_PROJECT_ROOT = Path(__file__).parent.parent

_DEFAULT_QR_IMAGE = str(
    _PROJECT_ROOT / "wecom-temp-54706-5859fb0aa9691999492c055b46355e8b.jpg"
)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    NCLOUD_BASE_URL: str = "http://nclouddl43.ywhzsoft.com:8154"
    NCLOUD_USERNAME: str = "测试"
    NCLOUD_PASSWORD: str = "123"
    NCLOUD_QR_IMAGE_PATH: str = _DEFAULT_QR_IMAGE


settings = Settings()
