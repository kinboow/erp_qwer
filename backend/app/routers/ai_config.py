"""AI 模型配置 API 路由"""

from __future__ import annotations

import time
from typing import Any, Optional

import httpx
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.models import User
from app.services.ai_config import (
    AI_PROVIDER_PRESETS,
    ensure_ai_config_table,
    get_ai_config,
    get_ai_config_for_parser,
    log_ai_call,
    mask_api_key,
    save_ai_config,
)

router = APIRouter(tags=["AI-模型配置"])


class AiConfigPayload(BaseModel):
    ai_provider: Optional[str] = None
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


@router.get("/providers", summary="获取 AI 供应商预设列表")
def api_get_ai_providers(
    current_user: User = Depends(get_current_user),
):
    return _json_response(data=AI_PROVIDER_PRESETS)


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


class AiTestPayload(BaseModel):
    """测试连接时可直接传入当前表单值，无需先保存"""
    ai_base_url: Optional[str] = None
    ai_api_key: Optional[str] = None
    ai_model: Optional[str] = None


@router.post("/test", summary="测试 AI 模型连接")
async def api_test_ai_connection(
    payload: AiTestPayload = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # 优先使用请求体传入的值，回退到 DB 配置
    db_cfg = get_ai_config_for_parser(db)
    base_url = ((payload and payload.ai_base_url) or "").strip() or db_cfg.get("base_url") or ""
    api_key = ((payload and payload.ai_api_key) or "").strip() or db_cfg.get("api_key") or ""
    model = ((payload and payload.ai_model) or "").strip() or db_cfg.get("model") or ""

    if not api_key:
        return _json_response(code=400, message="请先填写 API Key")
    if not base_url:
        return _json_response(code=400, message="请先填写 API 基地址")
    if not model:
        return _json_response(code=400, message="请先填写模型名称")

    t0 = time.time()
    try:
        base_url = base_url.rstrip("/")
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": "请回复OK"}],
                    "temperature": 0,
                },
            )
            resp.raise_for_status()
            data = resp.json()
        duration_ms = int((time.time() - t0) * 1000)
        usage = data.get("usage") or {}
        reply = (((data.get("choices") or [{}])[0].get("message") or {}).get("content") or "").strip()
        log_ai_call(
            db, model=model, caller="test_connection",
            prompt_tokens=usage.get("prompt_tokens", 0),
            completion_tokens=usage.get("completion_tokens", 0),
            total_tokens=usage.get("total_tokens", 0),
            duration_ms=duration_ms, status="success",
            request_summary="测试连接: 请回复OK",
            response_summary=reply[:500],
        )
        return _json_response(
            message="AI 连接测试成功",
            data={"model": model, "reply": reply},
        )
    except httpx.HTTPStatusError as exc:
        duration_ms = int((time.time() - t0) * 1000)
        status = exc.response.status_code
        body = exc.response.text[:200]
        log_ai_call(db, model=model, caller="test_connection", duration_ms=duration_ms, status="error", error_message=f"HTTP {status}: {body}")
        if status == 429:
            return _json_response(code=429, message="AI 接口限流（429），请稍后重试或检查 API Key 额度")
        elif status == 401:
            return _json_response(code=401, message="API Key 无效或已过期（401）")
        return _json_response(code=status, message=f"AI 接口错误({status}): {body}")
    except Exception as exc:
        duration_ms = int((time.time() - t0) * 1000)
        log_ai_call(db, model=model, caller="test_connection", duration_ms=duration_ms, status="error", error_message=str(exc)[:500])
        return _json_response(code=502, message=f"AI 连接测试失败: {exc}")


# ---------------------------------------------------------------------------
# AI 调用日志查询
# ---------------------------------------------------------------------------

@router.get("/call-logs", summary="AI 调用日志列表")
def api_get_ai_call_logs(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    caller: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    ensure_ai_config_table(db)
    conditions = []
    params: dict[str, Any] = {}
    if caller:
        conditions.append("caller = :caller")
        params["caller"] = caller
    if status:
        conditions.append("status = :status")
        params["status"] = status

    where = " AND ".join(conditions) if conditions else "1=1"
    total = db.execute(text(f"SELECT COUNT(*) FROM ai_call_logs WHERE {where}"), params).scalar() or 0

    offset = (page - 1) * page_size
    rows = db.execute(text(
        f"SELECT id, called_at, model, caller, prompt_tokens, completion_tokens, total_tokens, "
        f"duration_ms, status, error_message, request_summary, response_summary "
        f"FROM ai_call_logs WHERE {where} ORDER BY id DESC LIMIT :limit OFFSET :offset"
    ), {**params, "limit": page_size, "offset": offset}).mappings().all()

    logs = []
    for r in rows:
        logs.append({
            "id": r["id"],
            "called_at": str(r["called_at"] or ""),
            "model": r["model"] or "",
            "caller": r["caller"] or "",
            "prompt_tokens": r["prompt_tokens"] or 0,
            "completion_tokens": r["completion_tokens"] or 0,
            "total_tokens": r["total_tokens"] or 0,
            "duration_ms": r["duration_ms"] or 0,
            "status": r["status"] or "",
            "error_message": r["error_message"] or "",
            "request_summary": r["request_summary"] or "",
            "response_summary": r["response_summary"] or "",
        })

    return _json_response(data={"list": logs, "total": total, "page": page, "page_size": page_size})
