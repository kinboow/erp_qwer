"""
企微消息媒体归档服务 — 自动将图片/文件从 CDN 下载并永久存储到本地 OSS (MinIO)
"""

from __future__ import annotations

import logging
import mimetypes
import secrets
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


def _extract_cdn_params_from_payload(payload: dict[str, Any], message_type: str = "") -> dict[str, Any]:
    """从消息 payload 中提取 CDN 下载参数（返回首选方式）"""
    candidates = _extract_all_cdn_candidates(payload, message_type)
    return candidates[0] if candidates else {}


def _extract_all_cdn_candidates(payload: dict[str, Any], message_type: str = "") -> list[dict[str, Any]]:
    """从消息 payload 中提取所有可用的 CDN 下载候选参数（按优先级排列）。"""
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

    candidates: list[dict[str, Any]] = []

    file_id = c2c.get("file_id") or data.get("file_id") or ""
    if file_id and aes_key:
        candidates.append({
            "mode": "c2c_download",
            "file_id": file_id,
            "aes_key": aes_key,
            "file_size": size,
            "file_type": 1 if message_type in ("image", "img", "picture") else 5,
        })

    url_options: list[tuple[int, str]] = []
    for url_key, size_key in (("url", "size"), ("md_url", "md_size"), ("ld_url", "ld_size")):
        raw_url = cdn.get(url_key) or ""
        raw_size = cdn.get(size_key) or 0
        try:
            raw_size = int(raw_size)
        except (ValueError, TypeError):
            raw_size = 0
        if raw_url and raw_size:
            url_options.append((raw_size, str(raw_url)))

    if url and size:
        url_options.append((size, str(url)))

    url_options.sort(key=lambda item: item[0], reverse=True)
    seen_urls: set[str] = set()
    for candidate_size, candidate_url in url_options:
        if candidate_url in seen_urls:
            continue
        seen_urls.add(candidate_url)
        if auth_key and aes_key:
            candidates.append({
                "mode": "wx_download",
                "url": candidate_url,
                "auth_key": auth_key,
                "aes_key": aes_key,
                "size": candidate_size,
            })

    return candidates


def _resolve_runtime(db: Session, instance_id: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
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
    payload_wxid = _safe_text((payload or {}).get("wxid") or _find_first(payload or {}, ["wxid", "robot_id", "robotId"]))
    if row:
        host = (row.get("host") or "").strip()
        port = (row.get("port") or "").strip()
        base = host if host.startswith(("http://", "https://")) else f"http://{host}" if host else ""
        if base and port and port not in ("80", "443"):
            base = f"{base}:{port}"
        return {
            "api_base_url": base.rstrip("/"),
            "api_key": row.get("api_key") or "",
            "wxid": payload_wxid or row.get("selected_wxid") or instance_id,
        }
    return {"api_base_url": "", "api_key": "", "wxid": payload_wxid or instance_id}


async def _cdn_download_once(runtime: dict[str, Any], cdn_params: dict[str, Any], save_path: Path) -> Path:
    mode = cdn_params.get("mode", "wx_download")
    api_route = f"cdn/{mode}"
    request_body = {k: v for k, v in cdn_params.items() if k != "mode"}
    request_body["save_path"] = str(save_path)

    headers: dict[str, str] = {}
    if runtime.get("api_key"):
        headers["X-API-Key"] = runtime["api_key"]

    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(
            f"{runtime['api_base_url']}/api/{runtime['wxid']}/{api_route}",
            json=request_body,
            headers=headers,
        )
        resp.raise_for_status()
        resp_data = resp.json()

    if isinstance(resp_data, dict) and resp_data.get("code") not in (0, None):
        raise RuntimeError(resp_data.get("msg") or "CDN API 返回错误")

    actual_path = save_path
    if not actual_path.is_file():
        data_body = resp_data.get("data") if isinstance(resp_data.get("data"), dict) else {}
        for key in ("save_path", "path", "file_path"):
            possible = str(data_body.get(key) or "").strip()
            if possible and Path(possible).is_file():
                actual_path = Path(possible)
                break
    if not actual_path.is_file():
        raise RuntimeError("下载后文件不存在")
    return actual_path


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

    candidates = _extract_all_cdn_candidates(payload, message_type)
    if not candidates:
        logger.debug("[媒体归档] msg_log_id=%s 无CDN参数，跳过", msg_log_id)
        return None
 
    runtime = _resolve_runtime(db, instance_id, payload)
    if not runtime.get("api_base_url") or not runtime.get("wxid"):
        logger.warning("[媒体归档] msg_log_id=%s 缺少运行时配置", msg_log_id)
        return None
 
    ext = _guess_extension(file_name, message_type)
    download_dir = Path(__file__).resolve().parents[2] / "temp" / "media_archive"
    download_dir.mkdir(parents=True, exist_ok=True)
    attempts: list[tuple[str, dict[str, Any]]] = [(f"首选({candidates[0].get('mode')})", candidates[0])]
    if candidates:
        attempts.append((f"重试({candidates[0].get('mode')})", candidates[0]))
    for idx, candidate in enumerate(candidates[1:], start=1):
        attempts.append((f"备用{idx}({candidate.get('mode')})", candidate))

    last_err = ""
    for label, cdn_params in attempts:
        save_path = download_dir / f"msg_{msg_log_id}_{secrets.token_hex(4)}{ext}"
        actual_path: Path | None = None
        try:
            actual_path = await _cdn_download_once(runtime, cdn_params, save_path)
            file_bytes = actual_path.read_bytes()
            now = datetime.now()
            oss_key = f"wechat_media/{now.strftime('%Y/%m/%d')}/msg_{msg_log_id}{ext}"
            content_type = _guess_content_type(file_name or actual_path.name, message_type)
            oss_client.upload_file(oss_key, file_bytes, content_type=content_type)
            logger.info("[媒体归档] 已上传到OSS msg_log_id=%s oss_key=%s size=%d via=%s", msg_log_id, oss_key, len(file_bytes), label)
            db.execute(text(
                "UPDATE message_logs SET oss_key = :oss_key WHERE id = :id"
            ), {"oss_key": oss_key, "id": msg_log_id})
            db.commit()
            return oss_key
        except Exception as exc:
            last_err = str(exc)
            logger.warning("[媒体归档] 下载失败 msg_log_id=%s via=%s: %s", msg_log_id, label, exc)
        finally:
            try:
                if actual_path and actual_path.is_file():
                    actual_path.unlink(missing_ok=True)
                elif save_path.is_file():
                    save_path.unlink(missing_ok=True)
            except Exception:
                pass

    logger.warning("[媒体归档] 下载/上传失败 msg_log_id=%s: %s", msg_log_id, last_err or "未知错误")
    return None


async def ensure_oss_and_read(
    db: Session,
    msg_log_id: int,
    payload: dict[str, Any],
    instance_id: str,
    message_type: str,
    file_name: str = "",
) -> bytes | None:
    """
    确保媒体文件已归档到 OSS，然后从 OSS 读取并返回字节内容。

    流程：
    1. 检查 message_logs 是否已有 oss_key
    2. 若无，调用 download_and_archive 从 CDN 下载并归档到 OSS
    3. 从 OSS 读取文件内容返回

    返回 None 表示下载或读取失败。
    """
    oss_key = None

    # 检查是否已归档
    try:
        row = db.execute(text(
            "SELECT oss_key FROM message_logs WHERE id = :id"
        ), {"id": msg_log_id}).mappings().first()
        oss_key = (row.get("oss_key") or "") if row else ""
    except Exception:
        pass

    # 若未归档，先执行归档
    if not oss_key:
        oss_key = await download_and_archive(db, msg_log_id, payload, instance_id, message_type, file_name)

    if not oss_key:
        logger.warning("[OSS读取] 归档失败，无法获取文件 msg_log_id=%s", msg_log_id)
        return None

    # 从 OSS 读取
    try:
        file_bytes = oss_client.download_file(oss_key)
        logger.info("[OSS读取] 成功 msg_log_id=%s oss_key=%s size=%d", msg_log_id, oss_key, len(file_bytes))
        return file_bytes
    except Exception as exc:
        logger.warning("[OSS读取] 下载失败 msg_log_id=%s oss_key=%s: %s", msg_log_id, oss_key, exc)
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
