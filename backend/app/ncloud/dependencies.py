from __future__ import annotations

from fastapi import Request

from app.ncloud.client.erp_client import ERPClient


def get_erp_client(request: Request) -> ERPClient:
    """FastAPI dependency: get the shared ERPClient from app state."""
    return request.app.state.erp_client
