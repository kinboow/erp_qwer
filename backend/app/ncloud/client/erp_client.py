from __future__ import annotations

import re
from typing import Any

import httpx

from app.ncloud.client.erp_auth import ERPAuthManager, FORM_HEADERS
from app.ncloud.config import settings
from app.ncloud.exceptions import ERPAuthError, ERPBusinessError, ERPUpstreamError

_LOGIN_MESSAGE_PATTERN = re.compile(r"登录|login|session|expired|unauthorized", re.IGNORECASE)


def _is_session_expired(response: httpx.Response) -> bool:
    """Detect ERP session expiry from response."""
    # Check for redirect to login page
    if response.status_code in (301, 302):
        location = response.headers.get("location", "")
        if "/Login" in location or "/login" in location:
            return True
    # Check for 401
    if response.status_code == 401:
        return True
    # Check for Success:false with login-related message in 200 response
    if response.status_code == 200:
        try:
            payload = response.json()
            if not payload.get("Success", True):
                message = payload.get("Message", "") or ""
                if _LOGIN_MESSAGE_PATTERN.search(message):
                    return True
        except Exception:
            pass
    return False


class ERPClient:
    """Async ERP HTTP client with automatic session re-login."""

    def __init__(self, http_client: httpx.AsyncClient) -> None:
        self._http = http_client
        self._auth = ERPAuthManager(http_client)

    async def post_form(self, path: str, data: dict[str, Any]) -> dict[str, Any]:
        """POST form data to ERP. Retries once after session re-login if needed."""
        base_url = settings.NCLOUD_BASE_URL.rstrip("/")
        url = f"{base_url}{path}"

        await self._auth.login()

        try:
            response = await self._http.post(
                url,
                headers=FORM_HEADERS,
                data=data,
                timeout=30,
            )
        except httpx.RequestError as exc:
            raise ERPUpstreamError(f"ERP request failed: {exc}") from exc

        if _is_session_expired(response):
            # Session expired — re-login once and retry
            self._auth.invalidate()
            await self._auth.login(force=True)
            try:
                response = await self._http.post(
                    url,
                    headers=FORM_HEADERS,
                    data=data,
                    timeout=30,
                )
            except httpx.RequestError as exc:
                raise ERPUpstreamError(f"ERP request failed after re-login: {exc}") from exc

        if response.status_code >= 400:
            raise ERPUpstreamError(f"ERP HTTP {response.status_code}: {response.text[:200]}")

        try:
            payload = response.json()
        except Exception as exc:
            raise ERPUpstreamError(f"ERP returned non-JSON response: {response.text[:200]}") from exc

        if not payload.get("Success", True):
            message = payload.get("Message", "") or "ERP returned business error"
            if _LOGIN_MESSAGE_PATTERN.search(message):
                raise ERPAuthError(message)
            raise ERPBusinessError(message)

        return payload

    async def post_form_raw(self, path: str, data: dict[str, Any]) -> Any:
        """POST form data to ERP and return the raw parsed JSON (list or dict)."""
        base_url = settings.NCLOUD_BASE_URL.rstrip("/")
        url = f"{base_url}{path}"

        await self._auth.login()

        try:
            response = await self._http.post(
                url,
                headers=FORM_HEADERS,
                data=data,
                timeout=30,
            )
        except httpx.RequestError as exc:
            raise ERPUpstreamError(f"ERP request failed: {exc}") from exc

        if _is_session_expired(response):
            self._auth.invalidate()
            await self._auth.login(force=True)
            try:
                response = await self._http.post(
                    url,
                    headers=FORM_HEADERS,
                    data=data,
                    timeout=30,
                )
            except httpx.RequestError as exc:
                raise ERPUpstreamError(f"ERP request failed after re-login: {exc}") from exc

        if response.status_code >= 400:
            raise ERPUpstreamError(f"ERP HTTP {response.status_code}: {response.text[:200]}")

        try:
            return response.json()
        except Exception as exc:
            raise ERPUpstreamError(f"ERP returned non-JSON response: {response.text[:200]}") from exc
