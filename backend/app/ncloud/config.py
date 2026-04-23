"""ncloud 配置 — 直接复用 ERP 主配置，无需额外 .env 变量"""

from app.config import settings as _erp_settings


class _NcloudSettingsProxy:
    """将 ERP 主配置的 ERP_* 字段映射为 ncloud 内部使用的 NCLOUD_* 属性"""

    @property
    def NCLOUD_BASE_URL(self) -> str:
        return _erp_settings.ERP_BASE_URL or "http://nclouddl43.ywhzsoft.com:8154"

    @property
    def NCLOUD_USERNAME(self) -> str:
        return _erp_settings.ERP_USERNAME or "测试"

    @property
    def NCLOUD_PASSWORD(self) -> str:
        return _erp_settings.ERP_PASSWORD or "123"

    @property
    def NCLOUD_QR_IMAGE_PATH(self) -> str:
        return _erp_settings.ERP_QR_IMAGE_PATH or ""


settings = _NcloudSettingsProxy()
