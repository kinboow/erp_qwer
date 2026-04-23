"""ncloud 配置 — 直接复用 ERP 主配置，无需额外 .env 变量"""

from app.config import settings as _erp_settings


class _NcloudSettingsProxy:
    """将 ERP 主配置的 ERP_* 字段映射为 ncloud 内部使用的 NCLOUD_* 属性。
    支持通过 _override 字典在运行时热更新（保存配置后由 erp_sync.reload_erp_client 写入）。
    """

    _override: dict = {}

    @property
    def NCLOUD_BASE_URL(self) -> str:
        return self._override.get("NCLOUD_BASE_URL") or _erp_settings.ERP_BASE_URL or "http://nclouddl43.ywhzsoft.com:8154"

    @property
    def NCLOUD_USERNAME(self) -> str:
        return self._override.get("NCLOUD_USERNAME") or _erp_settings.ERP_USERNAME or "测试"

    @property
    def NCLOUD_PASSWORD(self) -> str:
        return self._override.get("NCLOUD_PASSWORD") or _erp_settings.ERP_PASSWORD or "123"

    @property
    def NCLOUD_QR_IMAGE_PATH(self) -> str:
        return self._override.get("NCLOUD_QR_IMAGE_PATH") or _erp_settings.ERP_QR_IMAGE_PATH or ""


settings = _NcloudSettingsProxy()
