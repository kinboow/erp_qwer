from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncGenerator

import httpx
from fastapi import FastAPI

from app.client.erp_client import ERPClient
from app.exceptions import register_exception_handlers
from app.routers import auth, base, inventory, reconciliation, sales_orders, shipments, unshipped_report


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    http_client = httpx.AsyncClient(
        headers={
            "User-Agent": "ncloud2api/0.2",
            "Accept": "application/json, text/javascript, */*; q=0.01",
        },
        follow_redirects=False,
        trust_env=False,
    )
    erp_client = ERPClient(http_client)

    app.state.http_client = http_client
    app.state.erp_client = erp_client

    yield

    await http_client.aclose()


app = FastAPI(title="ncloud2API", version="0.2.0", lifespan=lifespan)
register_exception_handlers(app)

app.include_router(auth.router)
app.include_router(base.router)
app.include_router(sales_orders.router)
app.include_router(shipments.router)
app.include_router(reconciliation.router)
app.include_router(unshipped_report.router)
app.include_router(inventory.router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
