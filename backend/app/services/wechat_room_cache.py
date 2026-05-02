"""
企微群聊名称缓存
启动时及定期从企微 API 拉取群聊列表，缓存 room_id → room_name 映射。
供审核列表等模块查询群聊名称使用。
"""

import asyncio
import logging
from datetime import datetime
from typing import Any, Optional

import httpx
from sqlalchemy import text

from app.database import SessionLocal

logger = logging.getLogger(__name__)

_room_cache: dict[str, str] = {}
_last_refreshed: Optional[str] = None
_refresh_task: Optional[asyncio.Task] = None
_refresh_lock = asyncio.Lock()


def get_room_name(room_id: str) -> str:
    """从缓存中查找 room_name，找不到返回空字符串"""
    return _room_cache.get(room_id, "")


def get_room_names(room_ids: list[str]) -> dict[str, str]:
    """批量查找 room_id → room_name"""
    return {rid: _room_cache[rid] for rid in room_ids if rid in _room_cache}


def get_all_cached_rooms() -> dict[str, str]:
    return dict(_room_cache)


def _load_wechat_config() -> dict[str, Any]:
    db = SessionLocal()
    try:
        row = db.execute(text("SELECT * FROM wechat_config WHERE id = 1")).mappings().first()
        return dict(row) if row else {}
    except Exception:
        return {}
    finally:
        db.close()


def _load_instances() -> list[dict[str, Any]]:
    db = SessionLocal()
    try:
        rows = db.execute(text("SELECT id, wxid, api_base_url, api_key FROM wechat_instances")).mappings().all()
        return [dict(r) for r in rows]
    except Exception:
        return []
    finally:
        db.close()


async def _fetch_rooms_from_instance(instance: dict[str, Any]) -> list[dict[str, str]]:
    """调用企微 API 获取某个实例的群聊列表"""
    api_base = (instance.get("api_base_url") or "").rstrip("/")
    wxid = instance.get("wxid") or ""
    api_key = instance.get("api_key") or ""

    if not api_base or not wxid:
        # 尝试从全局配置获取 base_url
        config = _load_wechat_config()
        host = (config.get("host") or "").strip()
        port = (config.get("port") or "").strip()
        if not host:
            return []
        if host.startswith(("http://", "https://")):
            api_base = host.rstrip("/")
        else:
            api_base = f"http://{host}"
        if port:
            api_base = f"{api_base}:{port}"
        if not api_key:
            api_key = (config.get("api_key") or "").strip()

    if not wxid:
        return []

    url = f"{api_base}/api/{wxid}/rooms/get"
    headers = {}
    if api_key:
        headers["X-API-Key"] = api_key

    rooms = []
    page_num = 1
    page_size = 100
    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=True, trust_env=False) as client:
            while True:
                resp = await client.post(url, json={"page_num": page_num, "page_size": page_size}, headers=headers)
                resp.raise_for_status()
                data = resp.json()
                if not isinstance(data, dict) or data.get("code") != 0:
                    break

                raw = data.get("data")
                page_list = _extract_rooms(raw if raw is not None else [])
                for item in page_list:
                    room_id, room_name = _parse_room(item)
                    if room_id and room_name:
                        rooms.append({"room_id": room_id, "room_name": room_name})

                if len(page_list) < page_size:
                    break
                page_num += 1
    except Exception as exc:
        logger.warning("[RoomCache] 获取群聊列表失败 wxid=%s: %s", wxid, exc)

    return rooms


def _extract_rooms(raw: Any) -> list:
    if isinstance(raw, list):
        return raw
    if isinstance(raw, dict):
        for key in ["room_list", "list", "items", "records", "rooms", "data"]:
            value = raw.get(key)
            if isinstance(value, list):
                return value
    return []


def _parse_room(item: Any) -> tuple[str, str]:
    if not isinstance(item, dict):
        return ("", "")
    room_id = (
        item.get("room_id") or item.get("roomId") or item.get("id")
        or item.get("conversation_id") or item.get("room_conversation_id") or ""
    )
    room_name = (
        item.get("room_name") or item.get("roomName") or item.get("name")
        or item.get("nickname") or item.get("nick_name") or ""
    )
    return (str(room_id).strip(), str(room_name).strip())


async def refresh_room_cache() -> int:
    """刷新全部实例的群聊名称缓存，返回总缓存数"""
    global _last_refreshed
    async with _refresh_lock:
        instances = _load_instances()
        new_cache: dict[str, str] = {}
        for inst in instances:
            rooms = await _fetch_rooms_from_instance(inst)
            for r in rooms:
                new_cache[r["room_id"]] = r["room_name"]

        if new_cache:
            _room_cache.clear()
            _room_cache.update(new_cache)
            _last_refreshed = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            logger.info("[RoomCache] 已刷新群聊缓存，共 %d 个群聊", len(_room_cache))

            # 同时回写到 DB 中的审核记录
            _backfill_review_room_names(new_cache)

        return len(_room_cache)


def _backfill_review_room_names(room_map: dict[str, str]):
    """把缓存中的群聊名称回写到审核记录和消息日志中空 room_name 的记录，
    同时修复 message_type='batch' 的历史数据"""
    db = SessionLocal()
    try:
        # 回写 room_name
        if room_map:
            for room_id, room_name in room_map.items():
                db.execute(
                    text(
                        "UPDATE downstream_order_reviews SET room_name = :room_name "
                        "WHERE room_id = :room_id AND (room_name IS NULL OR room_name = '')"
                    ),
                    {"room_id": room_id, "room_name": room_name},
                )
                db.execute(
                    text(
                        "UPDATE message_logs SET room_name = :room_name "
                        "WHERE room_id = :room_id AND (room_name IS NULL OR room_name = '')"
                    ),
                    {"room_id": room_id, "room_name": room_name},
                )

        # 修复 message_type='batch' → 从 message_logs 取真实类型
        db.execute(text(
            "UPDATE downstream_order_reviews r "
            "JOIN message_logs m ON r.msg_log_id = m.id "
            "SET r.message_type = m.message_type "
            "WHERE r.message_type = 'batch' AND m.message_type != '' AND m.message_type IS NOT NULL"
        ))

        # 从 message_logs 补全空 sender_name
        db.execute(text(
            "UPDATE downstream_order_reviews r "
            "JOIN message_logs m ON r.msg_log_id = m.id "
            "SET r.sender_name = m.sender_name "
            "WHERE (r.sender_name IS NULL OR r.sender_name = '') "
            "AND m.sender_name IS NOT NULL AND m.sender_name != ''"
        ))

        db.commit()
    except Exception as exc:
        logger.warning("[RoomCache] 回写失败: %s", exc)
        try:
            db.rollback()
        except Exception:
            pass
    finally:
        db.close()


async def _poll_loop(interval_seconds: int):
    # 启动后立即刷新一次
    await refresh_room_cache()
    while True:
        await asyncio.sleep(interval_seconds)
        await refresh_room_cache()


def start_room_cache_refresher(interval_seconds: int = 300):
    """启动群聊名称缓存定时刷新（默认 5 分钟）"""
    global _refresh_task
    if _refresh_task and not _refresh_task.done():
        return
    _refresh_task = asyncio.create_task(_poll_loop(interval_seconds))
    logger.info("[RoomCache] 已启动群聊缓存刷新，间隔 %s 秒", interval_seconds)


def stop_room_cache_refresher():
    global _refresh_task
    if _refresh_task and not _refresh_task.done():
        _refresh_task.cancel()
    _refresh_task = None
