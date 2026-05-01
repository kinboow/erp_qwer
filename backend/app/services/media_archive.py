"""
企微消息媒体归档服务 — 自动将图片/文件从 CDN 下载并永久存储到本地 OSS (MinIO)
"""

from __future__ import annotations

import logging
import mimetypes
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.utils.oss_client import oss_client

logger = logging.getLogger(__name__)


def _safe_text(v: Any) -> str:
    if v is None:
        return ""
    return str(v).strip()


def _find_first(sources: dict[str, Any] | Any, keys: list[str]) -> str:
    """从 payload 多层结构中查找第一个非空值"""
    if isinstance(sources, dict):
        for key in keys:
            # 先在顶层找
            val = sources.get(key)
            if val:
                return str(val)
            # 再在嵌套 dict 中找
            for sub in sources.values():
                if isinstance(sub, dict):
                    val = sub.get(key)
                    if val:
                        return str(val)
    return ""


def _extract_cdn_params_from_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """从消息 payload 中提取 CDN 下载参数"""
    message = payload.get("message") if isinstance(payload.get("message"), dict) else {}
    data = message.get("data") if isinstance(message.get("data"), dict) else {}
    cdn = data.get("cdn") if isinstance(data.get("cdn"), dict) else {}
    c2c = data.get("c2c_cdn") if isinstance(data.get("c2c_cdn"), dict) else {}

    url = cdn.get("url") or data.get("url") or payload.get("url") or ""
    auth_key = cdn.get("auth_key") or data.get("auth_key") or payload.get("auth_key") or ""
    aes_key = cdn.get("aes_key") or c2c.get("aes_key") or data.get("aes_key") or payload.get("aes_key") or ""
    size = cdn.get("size") or c2c.get("file_size") or c2c.get("size") or data.get("size") or 0
    try:
        size = int(size)
    except (ValueError, TypeError):
        size = 0

    if url and auth_key and aes_key and size:
        return {"mode": "wx_download", "url": url, "auth_key": auth_key, "aes_key": aes_key, "size": size}

    file_id = c2c.get("file_id") or data.get("file_id") or ""
    if file_id and aes_key:
        return {"mode": "c2c_download", "file_id": file_id, "aes_key": aes_key, "file_size": size, "file_type": 5}

    return {}


def _resolve_runtime(db: Session, instance_id: str) -> dict[str, Any]:
    """解析企微运行时配置"""
    if instance_id:
        try:
            from app.models import WechatInstance
            inst = db.query(WechatInstance).filter(
                (WechatInstance.wxid == instance_id) | (WechatInstance.id == instance_id)
            ).first()
            if inst:
                return {
                    "api_base_url": (inst.api_base_url or "").rstrip("/"),
                    "api_key": inst.api_key or "",
                    "wxid": inst.wxid or "",
                }
        except Exception:
            pass
    try:
        row = db.execute(text(
            "SELECT host, port, api_key, selected_wxid FROM wechat_config WHERE id = 1"
        )).mappings().first()
    except Exception:
        row = None
    if row:
        host = (row.get("host") or "").strip()
        port = (row.get("port") or "").strip()
        base = host if host.startswith(("http://", "https://")) else f"http://{host}" if host else ""
        if base and port and port not in ("80", "443"):
            base = f"{base}:{port}"
        return {
            "api_base_url": base.rstrip("/"),
            "api_key": row.get("api_key") or "",
            "wxid": row.get("selected_wxid") or instance_id,
        }
    return {"api_base_url": "", "api_key": "", "wxid": instance_id}


def _guess_extension(file_name: str, message_type: str) -> str:
    """根据文件名或消息类型推断扩展名"""
    if file_name:
        ext = Path(file_name).suffix.lower()
        if ext:
            return ext
    return ".png" if message_type in ("image", "img", "picture") else ".bin"


def _guess_content_type(file_name: str, message_type: str) -> str:
    """推断 MIME 类型"""
    if file_name:
        ct, _ = mimetypes.guess_type(file_name)
        if ct:
            return ct
    if message_type in ("image", "img", "picture"):
        return "image/png"
    return "application/octet-stream"


async def download_and_archive(
    db: Session,
    msg_log_id: int,
    payload: dict[str, Any],
    instance_id: str,
    message_type: str,
    file_name: str = "",
) -> str | None:
    """
    从企微 CDN 下载文件并上传到本地 OSS，返回 oss_key。
    如果已存在 oss_key 则跳过。
    """
    # 检查是否已归档
    row = db.execute(text(
        "SELECT oss_key FROM message_logs WHERE id = :id"
    ), {"id": msg_log_id}).mappings().first()
    if row and row.get("oss_key"):
        return row["oss_key"]

    cdn_params = _extract_cdn_params_from_payload(payload)
    if not cdn_params:
        logger.debug("[媒体归档] msg_log_id=%s 无CDN参数，跳过", msg_log_id)
        return None

    runtime = _resolve_runtime(db, instance_id)
    if not runtime.get("api_base_url") or not runtime.get("wxid"):
        logger.warning("[媒体归档] msg_log_id=%s 缺少运行时配置", msg_log_id)
        return None

    # 下载到临时目录
    ext = _guess_extension(file_name, message_type)
    download_dir = Path(__file__).resolve().parents[2] / "temp" / "media_archive"
    download_dir.mkdir(parents=True, exist_ok=True)
    save_path = download_dir / f"msg_{msg_log_id}{ext}"

    mode = cdn_params.pop("mode")
    api_route = f"cdn/{mode}"
    cdn_params["save_path"] = str(save_path)

    headers: dict[str, str] = {}
    if runtime.get("api_key"):
        headers["X-API-Key"] = runtime["api_key"]

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                f"{runtime['api_base_url']}/api/{runtime['wxid']}/{api_route}",
                json=cdn_params,
                headers=headers,
            )
            resp.raise_for_status()
            resp_data = resp.json()

        if isinstance(resp_data, dict) and resp_data.get("code") not in (0, None):
            logger.warning("[媒体归档] CDN API 返回错误 msg_log_id=%s: %s", msg_log_id, resp_data.get("msg"))
            return None

        # 检查文件是否存在
        if not save_path.is_file():
            data_body = resp_data.get("data") if isinstance(resp_data.get("data"), dict) else {}
            for key in ("save_path", "path", "file_path"):
                possible = str(data_body.get(key) or "").strip()
                if possible and Path(possible).is_file():
                    save_path = Path(possible)
                    break
        if not save_path.is_file():
            logger.warning("[媒体归档] 下载后文件不存在 msg_log_id=%s", msg_log_id)
            return None

        # 上传到 OSS
        file_bytes = save_path.read_bytes()
        now = datetime.now()
        oss_key = f"wechat_media/{now.strftime('%Y/%m/%d')}/msg_{msg_log_id}{ext}"
        content_type = _guess_content_type(file_name or save_path.name, message_type)

        oss_client.upload_file(oss_key, file_bytes, content_type=content_type)
        logger.info("[媒体归档] 已上传到OSS msg_log_id=%s oss_key=%s size=%d", msg_log_id, oss_key, len(file_bytes))

        # 更新 message_logs
        db.execute(text(
            "UPDATE message_logs SET oss_key = :oss_key WHERE id = :id"
        ), {"oss_key": oss_key, "id": msg_log_id})
        db.commit()

        # 清理临时文件
        try:
            save_path.unlink(missing_ok=True)
        except Exception:
            pass

        return oss_key

    except Exception as exc:
        logger.warning("[媒体归档] 下载/上传失败 msg_log_id=%s: %s", msg_log_id, exc)
        return None


async def download_and_archive_background(
    msg_log_id: int,
    payload: dict[str, Any],
    instance_id: str,
    message_type: str,
    file_name: str = "",
) -> None:
    """后台异步任务：下载并归档媒体文件"""
    db = SessionLocal()
    try:
        await download_and_archive(db, msg_log_id, payload, instance_id, message_type, file_name)
    except Exception as exc:
        logger.warning("[媒体归档] 后台任务异常 msg_log_id=%s: %s", msg_log_id, exc)
    finally:
        db.close()
