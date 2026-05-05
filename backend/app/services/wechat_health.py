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
_recovering: bool = False          # True = 正在尝试自动重启，不显示离线
_recovery_task: asyncio.Task | None = None


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


def _is_truthy(val) -> bool:
    """判断 API 返回值是否表示"真"，兼容 bool / int / str 各种格式"""
    if val is None:
        return False
    if isinstance(val, bool):
        return val
    if isinstance(val, (int, float)):
        return val > 0
    if isinstance(val, str):
        return val.lower() in ("true", "1", "yes", "online", "running")
    return bool(val)


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

            # 按 wxid 匹配，可能有多个实例（多开），优先选 login_status=true 的
            matched = [i for i in instances if i.get("wxid") == selected_wxid]
            if not matched:
                wxids = [i.get("wxid", "?") for i in instances]
                return False, f"实例 {selected_wxid} 不在运行列表中（现有: {wxids}）"

            # 优先取已登录的实例，否则取第一个
            inst = next((i for i in matched if _is_truthy(i.get("login_status"))), matched[0])

            nickname = inst.get('nickname') or selected_wxid
            raw_status = inst.get("status")
            raw_attached = inst.get("attached")
            raw_login = inst.get("login_status")

            logger.info("[WeChat Health] 实例 %s 原始字段: status=%r, attached=%r, login_status=%r, pid=%r",
                        nickname, raw_status, raw_attached, raw_login, inst.get("pid"))

            # 判断已登录：仅以 login_status 为准（nickname 可能是历史缓存，不可靠）
            if not _is_truthy(raw_login):
                return False, f"实例 {nickname} 未登录（login_status={raw_login}）"

            return True, ""
    except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
        return False, f"API 服务不可达：{exc}"
    except Exception as exc:
        return False, f"检查实例状态失败：{exc}"


async def _check_once() -> None:
    config = _load_wechat_config()

    host = (config.get("host") or "").strip()
    port = (config.get("port") or "").strip()
    if not host:
        _status.update({
            "online": False,
            "last_checked_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
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
    selected_wxid = (config.get("selected_wxid") or "").strip()
    if not selected_wxid:
        _status.update({
            "online": False,
            "last_checked_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "last_error": "未选择企微实例（selected_wxid 为空）",
        })
        return

    # 统一通过 overview 接口判断：API 可达性 + 实例登录状态
    ok, reason = await _check_instance_status(base_url, api_key, selected_wxid)
    if not ok:
        _status.update({
            "online": False,
            "last_checked_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "last_error": reason,
        })
        return

    _status.update({
        "online": True,
        "last_checked_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "last_error": None,
    })


async def _try_auto_restart() -> None:
    """尝试自动重启微信实例，最多重试 2 次，每次等待 10 秒后检查"""
    global _recovering, _prev_online
    _recovering = True
    config = _load_wechat_config()

    host = (config.get("host") or "").strip()
    port = (config.get("port") or "").strip()
    api_key = (config.get("api_key") or "").strip()

    if host.startswith(("http://", "https://")):
        base_url = host.rstrip("/")
    else:
        base_url = f"http://{host}"
    if port:
        base_url = f"{base_url}:{port}"

    headers = {}
    if api_key:
        headers["X-API-Key"] = api_key

    max_attempts = 2
    logged_in_inst = None

    for attempt in range(1, max_attempts + 1):
        logger.info("[WeChat Health] 自动恢复第 %d/%d 次尝试", attempt, max_attempts)

        # 调用 /api/wechat/start (force_new=false)
        try:
            async with httpx.AsyncClient(timeout=30, follow_redirects=True, trust_env=False) as client:
                resp = await client.post(
                    f"{base_url}/api/wechat/start",
                    json={"force_new": False},
                    headers=headers,
                )
                result = resp.json() if resp.status_code < 500 else {}
                logger.info("[WeChat Health] 第 %d 次重启请求: status=%d result=%s", attempt, resp.status_code, str(result)[:300])
        except Exception as exc:
            logger.warning("[WeChat Health] 第 %d 次重启请求失败: %s", attempt, exc)

        # 等待 10 秒
        await asyncio.sleep(10)

        # 通过 overview 查找已登录的实例
        try:
            async with httpx.AsyncClient(timeout=10, follow_redirects=True, trust_env=False) as client:
                resp = await client.post(
                    f"{base_url}/api/wechat/overview",
                    json={"only_attached": False},
                    headers=headers,
                )
                resp.raise_for_status()
                result = resp.json()
                if result.get("code") == 0:
                    raw_data = result.get("data", {})
                    instances = raw_data.get("instances", []) if isinstance(raw_data, dict) else (raw_data if isinstance(raw_data, list) else [])
                    for inst in instances:
                        if _is_truthy(inst.get("login_status")):
                            if inst.get("wxid") == config.get("selected_wxid", "").strip():
                                logged_in_inst = inst
                                break
                            if not logged_in_inst:
                                logged_in_inst = inst
        except Exception as exc:
            logger.warning("[WeChat Health] 第 %d 次恢复后查询 overview 失败: %s", attempt, exc)

        if logged_in_inst:
            logger.info("[WeChat Health] 第 %d 次尝试恢复成功", attempt)
            break
        elif attempt < max_attempts:
            logger.info("[WeChat Health] 第 %d 次尝试未恢复，将重试", attempt)

    _recovering = False

    if logged_in_inst:
        new_wxid = logged_in_inst.get("wxid", "")
        nickname = logged_in_inst.get("nickname", new_wxid)
        logger.info("[WeChat Health] 自动恢复成功，已登录实例: wxid=%s nickname=%s", new_wxid, nickname)

        # 自动选择已登录的实例
        old_wxid = (config.get("selected_wxid") or "").strip()
        if new_wxid and new_wxid != old_wxid:
            try:
                db = SessionLocal()
                try:
                    db.execute(
                        text("UPDATE wechat_config SET selected_wxid = :wxid WHERE id = 1"),
                        {"wxid": new_wxid},
                    )
                    db.commit()
                    logger.info("[WeChat Health] 已自动切换 selected_wxid: %s -> %s", old_wxid, new_wxid)
                finally:
                    db.close()
            except Exception as exc:
                logger.warning("[WeChat Health] 更新 selected_wxid 失败: %s", exc)

        _status.update({
            "online": True,
            "last_checked_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "last_error": None,
        })
        _prev_online = True
        try:
            from app.services import ws_notify
            await ws_notify.broadcast("wechat_online")
        except Exception:
            pass
        try:
            from app.services.system_messages import create_system_message_background
            create_system_message_background(
                title="企业微信自动恢复成功",
                content=f"企业微信已通过自动重启恢复连接，当前实例: {nickname}",
                level="info",
                source="wechat_health",
            )
        except Exception:
            pass
        # 同时重连 WS
        try:
            from app.services.wechat_ws_service import wechat_ws_service
            await wechat_ws_service.auto_connect_from_saved_config()
        except Exception:
            pass
    else:
        await _check_once()
        _prev_online = _status.get("online", False)
        logger.warning("[WeChat Health] 自动恢复失败，仍然离线: %s", _status.get("last_error"))
        # 恢复失败，通知前端显示离线
        try:
            from app.services import ws_notify
            await ws_notify.broadcast("wechat_offline", {"error": _status.get("last_error") or ""})
        except Exception:
            pass
        try:
            from app.services.system_messages import create_system_message_background
            create_system_message_background(
                title="企业微信自动恢复失败",
                content=f"企业微信自动重启 {max_attempts} 次均失败，请手动处理。原因：{_status.get('last_error') or '未知'}",
                level="error",
                source="wechat_health",
            )
        except Exception:
            pass
        # 服务器语音告警
        try:
            from app.services.voice_alert import speak_alert
            speak_alert("企业微信已掉线，请快速处理！", repeat=3)
        except Exception:
            pass


async def refresh_wechat_health_status() -> dict[str, Any]:
    """立即执行一次微信状态检查并返回最新状态"""
    global _prev_online, _recovery_task
    async with _check_lock:
        await _check_once()
        current_online = _status.get("online", False)

        # 状态由在线变为离线时：写入紧急系统动态 + 系统消息 + 发起自动重启
        if _prev_online is not None and _prev_online and not current_online:
            error_msg = _status.get("last_error") or "未知原因"
            try:
                from app.services.system_activities import create_activity_background
                create_activity_background(
                    title="微信连接服务离线",
                    content=f"微信连接检测失败：{error_msg}，已发起自动重启",
                    type="urgent",
                    source="wechat_health",
                )
            except Exception:
                pass
            try:
                from app.services.system_messages import create_system_message_background
                create_system_message_background(
                    title="企业微信连接离线",
                    content=f"企业微信连接检测失败：{error_msg}，系统已发起自动重启",
                    level="error",
                    source="wechat_health",
                )
            except Exception:
                pass

            # 发起自动重启（后台任务，不阻塞）
            if not _recovery_task or _recovery_task.done():
                _recovery_task = asyncio.create_task(_try_auto_restart())
                logger.info("[WeChat Health] 已发起自动重启任务")

        # 状态由离线变为在线时，通知前端 + 写系统消息
        if _prev_online is not None and not _prev_online and current_online:
            try:
                from app.services import ws_notify
                await ws_notify.broadcast("wechat_online")
            except Exception:
                pass
            try:
                from app.services.system_messages import create_system_message_background
                create_system_message_background(
                    title="企业微信连接已恢复",
                    content="企业微信连接已恢复正常",
                    level="info",
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


def start_wechat_health_checker(interval_seconds: int = 3) -> None:
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
        "recovering": _recovering,
        "last_checked_at": _status.get("last_checked_at"),
        "last_error": _status.get("last_error"),
        "polling": _poll_task is not None and not _poll_task.done() if _poll_task else False,
    }
