"""
企业微信服务健康检查
逻辑：
1. 调用配置的 API /api/health 健康检查
2. 如果联通，检查是否有已绑定的实例且该实例已登录（status=1）
3. 两项都满足才算在线
"""

import asyncio
import logging
from datetime import datetime
from typing import Any

import httpx
from sqlalchemy import text

from app.database import SessionLocal

logger = logging.getLogger(__name__)

_poll_task: asyncio.Task | None = None
_check_lock = asyncio.Lock()
_status: dict[str, Any] = {
    "online": False,
    "last_checked_at": None,
    "last_error": "尚未检测",
}


def _load_wechat_config() -> dict[str, Any]:
    """从数据库读取企微全局配置"""
    db = SessionLocal()
    try:
        row = db.execute(text("SELECT * FROM wechat_config WHERE id = 1")).mappings().first()
        return dict(row) if row else {}
    except Exception:
        return {}
    finally:
        db.close()


def _check_bound_instance_logged_in(config: dict[str, Any]) -> tuple[bool, str]:
    """检查是否有绑定实例且已登录"""
    bound_id = config.get("bound_instance_id")
    selected_wxid = (config.get("selected_wxid") or "").strip()

    if not bound_id and not selected_wxid:
        return False, "未选择绑定实例"

    db = SessionLocal()
    try:
        if bound_id:
            row = db.execute(
                text("SELECT id, wxid, status FROM wechat_instances WHERE id = :id LIMIT 1"),
                {"id": int(bound_id)},
            ).mappings().first()
        else:
            row = db.execute(
                text("SELECT id, wxid, status FROM wechat_instances WHERE wxid = :wxid LIMIT 1"),
                {"wxid": selected_wxid},
            ).mappings().first()

        if not row:
            return False, "绑定的实例不存在"

        if row["status"] != 1:
            return False, f"实例 {row['wxid']} 未登录"

        return True, ""
    except Exception as exc:
        return False, f"检查实例状态失败：{exc}"
    finally:
        db.close()


async def _check_once() -> None:
    config = _load_wechat_config()

    host = (config.get("host") or "").strip()
    port = (config.get("port") or "").strip()
    if not host:
        _status.update({
            "online": False,
            "last_checked_at": datetime.now().isoformat(),
            "last_error": "未配置企微 API 地址",
        })
        return

    # 构建 API base URL
    if host.startswith(("http://", "https://")):
        base_url = host.rstrip("/")
    else:
        base_url = f"http://{host}"
    if port:
        base_url = f"{base_url}:{port}"

    api_key = (config.get("api_key") or "").strip()
    headers = {}
    if api_key:
        headers["X-API-Key"] = api_key

    # 步骤 1：健康检查
    try:
        async with httpx.AsyncClient(timeout=8, follow_redirects=True, trust_env=False) as client:
            resp = await client.get(f"{base_url}/api/health", headers=headers)
            resp.raise_for_status()
    except Exception as exc:
        _status.update({
            "online": False,
            "last_checked_at": datetime.now().isoformat(),
            "last_error": f"API 服务不可达：{exc}",
        })
        return

    # 步骤 2：检查绑定实例是否已登录
    logged_in, reason = _check_bound_instance_logged_in(config)
    if not logged_in:
        _status.update({
            "online": False,
            "last_checked_at": datetime.now().isoformat(),
            "last_error": reason,
        })
        return

    _status.update({
        "online": True,
        "last_checked_at": datetime.now().isoformat(),
        "last_error": None,
    })


async def refresh_wechat_health_status() -> dict[str, Any]:
    """立即执行一次企微状态检查并返回最新状态"""
    async with _check_lock:
        await _check_once()
        return get_wechat_health_status()


async def _poll_loop(interval_seconds: int) -> None:
    while True:
        await refresh_wechat_health_status()
        await asyncio.sleep(interval_seconds)


def start_wechat_health_checker(interval_seconds: int = 30) -> None:
    global _poll_task
    if _poll_task and not _poll_task.done():
        return
    _poll_task = asyncio.create_task(_poll_loop(interval_seconds))
    logger.info("[WeChat Health] 已启动健康检查轮询，间隔 %s 秒", interval_seconds)


def stop_wechat_health_checker() -> None:
    global _poll_task
    if _poll_task and not _poll_task.done():
        _poll_task.cancel()
    _poll_task = None


def get_wechat_health_status() -> dict[str, Any]:
    return {
        "online": bool(_status.get("online", False)),
        "last_checked_at": _status.get("last_checked_at"),
        "last_error": _status.get("last_error"),
        "polling": _poll_task is not None and not _poll_task.done() if _poll_task else False,
    }
