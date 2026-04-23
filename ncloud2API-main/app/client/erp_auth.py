from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import httpx

from app.config import settings
from app.exceptions import ERPAuthError, ERPUpstreamError

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
        """Call CheckAccountSet with the QR image file to get qrcode + accountSetName."""
        qr_path = Path(settings.NCLOUD_QR_IMAGE_PATH)
        if not qr_path.is_absolute():
            # Resolve relative to project root (parent of app/)
            qr_path = Path(__file__).parent.parent.parent / qr_path
        if not qr_path.is_file():
            raise ERPAuthError(f"二维码图片不存在: {qr_path}")

        with open(qr_path, "rb") as f:
            files = {"imgData": (qr_path.name, f, "image/jpeg")}
            try:
                response = await self._client.post(
                    f"{settings.NCLOUD_BASE_URL.rstrip('/')}/Login/CheckAccountSet",
                    headers=AJAX_HEADERS,
                    files=files,
                    timeout=30,
                )
            except httpx.RequestError as exc:
                raise ERPUpstreamError(f"CheckAccountSet request failed: {exc}") from exc

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

            account_set = await self.resolve_account_set()

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
            except httpx.RequestError as exc:
                raise ERPUpstreamError(f"CheckLogin request failed: {exc}") from exc

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
