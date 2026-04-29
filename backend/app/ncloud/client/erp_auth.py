from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import httpx

from app.ncloud.config import settings
from app.ncloud.exceptions import ERPAuthError, ERPUpstreamError

AJAX_HEADERS = {"X-Requested-With": "XMLHttpRequest"}
FORM_HEADERS = {
    **AJAX_HEADERS,
    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
}


class ERPAuthManager:
    """Handles ERP login and session management with async lock to prevent concurrent re-logins."""

    def __init__(self, client: httpx.AsyncClient) -> None:
        self._client = client
        self._lock = asyncio.Lock()
        self._logged_in = False
        self._last_account_set: dict[str, Any] | None = None

    async def resolve_account_set(self) -> dict[str, Any]:
        """Call CheckAccountSet with the QR image file to get qrcode + accountSetName.
        Supports both local file path and HTTP/HTTPS URL for the QR image.
        """
        qr_source = settings.NCLOUD_QR_IMAGE_PATH
        if not qr_source:
            raise ERPAuthError("未配置账套二维码图片路径")

        if qr_source.startswith(("http://", "https://")):
            # Download image from MinIO via SDK (private bucket)
            try:
                from app.utils.oss_client import oss_client
                object_name = oss_client.parse_object_name(qr_source)
                if not object_name:
                    raise ERPAuthError(f"无法解析 MinIO 路径: {qr_source}")
                img_bytes = oss_client.download_file(object_name)
            except ERPAuthError:
                raise
            except Exception as exc:
                raise ERPUpstreamError(f"从 MinIO 下载二维码图片失败: {exc}") from exc
            filename = qr_source.rsplit("/", 1)[-1].split("?")[0] or "qr.jpg"
        else:
            # Local file path
            qr_path = Path(qr_source)
            if not qr_path.is_absolute():
                qr_path = Path(__file__).parent.parent.parent / qr_path
            if not qr_path.is_file():
                raise ERPAuthError(f"二维码图片不存在: {qr_path}")
            img_bytes = qr_path.read_bytes()
            filename = qr_path.name

        files = {"imgData": (filename, img_bytes, "image/jpeg")}
        last_exc: Exception | None = None
        for _attempt in range(3):
            try:
                response = await self._client.post(
                    f"{settings.NCLOUD_BASE_URL.rstrip('/')}/Login/CheckAccountSet",
                    headers=AJAX_HEADERS,
                    files=files,
                    timeout=30,
                )
                break
            except httpx.RequestError as exc:
                last_exc = exc
                await asyncio.sleep(2)
        else:
            raise ERPUpstreamError(f"CheckAccountSet request failed: {last_exc}") from last_exc

        if response.status_code >= 400:
            raise ERPUpstreamError(f"CheckAccountSet HTTP {response.status_code}")

        payload = response.json()
        if not payload.get("Success"):
            raise ERPAuthError(payload.get("Message") or "二维码账套识别失败")

        data = payload["Data"]
        return {
            "account_set_name": data["accountSetName"],
            "qrcode": data["qrcode"],
            "project_url": data.get("projectURL"),
        }

    async def login(self, force: bool = False) -> None:
        """Perform ERP login. Uses asyncio.Lock to prevent concurrent re-logins."""
        async with self._lock:
            if self._logged_in and not force:
                return

            # 复用上次解析的账套信息，避免每次重新下载二维码
            if self._last_account_set:
                account_set = self._last_account_set
            else:
                account_set = await self.resolve_account_set()

            last_exc = None
            for _attempt in range(3):
                try:
                    response = await self._client.post(
                        f"{settings.NCLOUD_BASE_URL.rstrip('/')}/Login/CheckLogin",
                        headers=FORM_HEADERS,
                        data={
                            "Account": settings.NCLOUD_USERNAME,
                            "Password": settings.NCLOUD_PASSWORD,
                            "qrcode": account_set["qrcode"],
                        },
                        timeout=30,
                    )
                    break
                except httpx.RequestError as exc:
                    last_exc = exc
                    await asyncio.sleep(2)
            else:
                raise ERPUpstreamError(f"CheckLogin request failed: {last_exc}") from last_exc

            if response.status_code >= 400:
                raise ERPUpstreamError(f"CheckLogin HTTP {response.status_code}")

            payload = response.json()
            login_rs = str(payload.get("rs", ""))
            if login_rs != "3":
                raise ERPAuthError(f"登录失败, rs={login_rs}")

            self._logged_in = True
            self._last_account_set = account_set

    def invalidate(self) -> None:
        """Mark session as invalid so next request triggers re-login."""
        self._logged_in = False
