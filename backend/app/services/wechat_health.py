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
_prev_online: bool | None = None


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


async def _check_instance_status(base_url: str, api_key: str, selected_wxid: str) -> tuple[bool, str]:
    """通过 live API 检查选中实例是否已登录且运行中"""
    headers = {}
    if api_key:
        headers["X-API-Key"] = api_key

    try:
        async with httpx.AsyncClient(timeout=10, follow_redirects=True, trust_env=False) as client:
            resp = await client.post(
                f"{base_url}/api/wechat/overview",
                json={"only_attached": False},
                headers=headers
            )
            resp.raise_for_status()
            result = resp.json()
            if result.get("code") != 0:
                return False, f"获取实例概览失败：{result.get('msg', '')}"

            raw_data = result.get("data", {})
            instances = raw_data.get("instances", []) if isinstance(raw_data, dict) else (raw_data if isinstance(raw_data, list) else [])

            # 尝试按 wxid 精确匹配；如果找不到，尝试按 nickname 或其他标识匹配
            inst = next((i for i in instances if i.get("wxid") == selected_wxid), None)
            if not inst:
                # 列出所有实例的 wxid 帮助排查
                wxids = [i.get("wxid", "?") for i in instances]
                return False, f"实例 {selected_wxid} 不在运行列表中（现有: {wxids}）"

            nickname = inst.get('nickname') or selected_wxid
            is_running = inst.get("status") or inst.get("attached")
            is_logged_in = inst.get("login_status")
            logger.debug("[WeChat Health] 实例 %s: status=%s, attached=%s, login_status=%s",
                         nickname, inst.get("status"), inst.get("attached"), inst.get("login_status"))

            if not is_running:
                return False, f"实例 {nickname} 未运行（status={inst.get('status')}, attached={inst.get('attached')}）"
            if not is_logged_in:
                return False, f"实例 {nickname} 未登录（login_status={inst.get('login_status')}）"

            return True, ""
    except Exception as exc:
        return False, f"检查实例状态失败：{exc}"


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

    # 步骤 2：根据是否有选中实例决定判断方式
    selected_wxid = (config.get("selected_wxid") or "").strip()
    if selected_wxid:
        # 有选中实例：必须运行中 + 已登录才算在线
        ok, reason = await _check_instance_status(base_url, api_key, selected_wxid)
        if not ok:
            _status.update({
                "online": False,
                "last_checked_at": datetime.now().isoformat(),
                "last_error": reason,
            })
            return

    # 没有选中实例时，健康检查通过即算在线
    _status.update({
        "online": True,
        "last_checked_at": datetime.now().isoformat(),
        "last_error": None,
    })


async def refresh_wechat_health_status() -> dict[str, Any]:
    """立即执行一次企微状态检查并返回最新状态"""
    global _prev_online
    async with _check_lock:
        await _check_once()
        current_online = _status.get("online", False)

        # 状态由在线变为离线时，写入紧急系统动态
        if _prev_online is not None and _prev_online and not current_online:
            error_msg = _status.get("last_error") or "未知原因"
            try:
                from app.services.system_activities import create_activity_background
                create_activity_background(
                    title="企微连接服务离线",
                    content=f"企微连接检测失败：{error_msg}",
                    type="urgent",
                    source="wechat_health",
                )
            except Exception:
                pass

        _prev_online = current_online
        return get_wechat_health_status()


async def _poll_loop(interval_seconds: int) -> None:
    while True:
        await refresh_wechat_health_status()
        await asyncio.sleep(interval_seconds)


def start_wechat_health_checker(interval_seconds: int = 20) -> None:
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
