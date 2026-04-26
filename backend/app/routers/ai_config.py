"""AI 模型配置 API 路由"""

from __future__ import annotations

from typing import Any, Optional

import httpx
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.models import User
from app.services.ai_config import (
    get_ai_config,
    get_ai_config_for_parser,
    mask_api_key,
    save_ai_config,
)

router = APIRouter(tags=["AI-模型配置"])


class AiConfigPayload(BaseModel):
    ai_base_url: Optional[str] = None
    ai_api_key: Optional[str] = None
    ai_model: Optional[str] = None
    ai_vision_model: Optional[str] = None
    ai_temperature: Optional[str] = None
    ai_enabled: Optional[str] = None


def _json_response(code: int = 200, message: str = "success", data: Any = None) -> dict:
    resp: dict[str, Any] = {"code": code, "message": message}
    if data is not None:
        resp["data"] = data
    return resp


@router.get("/config", summary="获取 AI 模型配置")
def api_get_ai_config(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    cfg = get_ai_config(db)
    # 脱敏 API Key
    cfg["ai_api_key"] = mask_api_key(cfg.get("ai_api_key") or "")
    return _json_response(data=cfg)


@router.put("/config", summary="保存 AI 模型配置")
def api_save_ai_config(
    payload: AiConfigPayload,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    data = payload.model_dump(exclude_none=True)
    cfg = save_ai_config(db, data)
    cfg["ai_api_key"] = mask_api_key(cfg.get("ai_api_key") or "")
    return _json_response(message="配置已保存", data=cfg)


@router.post("/test", summary="测试 AI 模型连接")
async def api_test_ai_connection(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    cfg = get_ai_config_for_parser(db)
    if not cfg.get("api_key"):
        return _json_response(code=400, message="请先配置 API Key")
    if not cfg.get("base_url"):
        return _json_response(code=400, message="请先配置 API 基地址")

    try:
        base_url = cfg["base_url"].rstrip("/")
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                f"{base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {cfg['api_key']}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": cfg["model"],
                    "messages": [{"role": "user", "content": "你好，请回复OK"}],
                    "max_tokens": 10,
                    "temperature": 0,
                },
            )
            resp.raise_for_status()
            data = resp.json()
        reply = (((data.get("choices") or [{}])[0].get("message") or {}).get("content") or "").strip()
        return _json_response(
            message="AI 连接测试成功",
            data={"model": cfg["model"], "reply": reply},
        )
    except Exception as exc:
        return _json_response(code=502, message=f"AI 连接测试失败: {exc}")
