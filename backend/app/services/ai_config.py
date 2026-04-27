"""
AI 模型配置读写服务 — 存储在 ai_config 表（key-value 模式）
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import settings

logger = logging.getLogger(__name__)

_DDL_AI_CONFIG = """
CREATE TABLE IF NOT EXISTS ai_config (
    id           INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    config_key   VARCHAR(100) NOT NULL UNIQUE,
    config_value TEXT NULL,
    updated_at   DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
"""

_AI_CONFIG_DEFAULTS: dict[str, str] = {
    "ai_base_url": "https://open.bigmodel.cn/api/paas/v4",
    "ai_api_key": "",
    "ai_model": "glm-4.6v-flash",
    "ai_vision_model": "glm-4.6v-flash",
    "ai_temperature": "0.1",
    "ai_enabled": "true",
}


def ensure_ai_config_table(db: Session) -> None:
    db.execute(text(_DDL_AI_CONFIG))
    db.commit()


def get_ai_config(db: Session) -> dict[str, Any]:
    """从数据库读取 AI 配置，不存在的 key 用默认值填充"""
    ensure_ai_config_table(db)
    rows = db.execute(text("SELECT config_key, config_value FROM ai_config")).mappings().all()
    cfg = {r["config_key"]: r["config_value"] for r in rows}
    for k, v in _AI_CONFIG_DEFAULTS.items():
        cfg.setdefault(k, v)
    cfg["ai_enabled"] = str(cfg.get("ai_enabled", "true")).lower() in ("true", "1", "yes")
    return cfg


def get_ai_config_for_parser(db: Session) -> dict[str, Any]:
    """供 ai_order_parser 调用，返回合并后的最终配置（DB 优先，.env 回退）"""
    cfg = get_ai_config(db)
    return {
        "base_url": (cfg.get("ai_base_url") or "").strip() or settings.OPENAI_BASE_URL,
        "api_key": (cfg.get("ai_api_key") or "").strip() or settings.OPENAI_API_KEY,
        "model": (cfg.get("ai_model") or "").strip() or settings.OPENAI_MODEL,
        "vision_model": (cfg.get("ai_vision_model") or "").strip() or settings.OPENAI_VISION_MODEL,
        "temperature": float(cfg.get("ai_temperature") or 0.1),
        "enabled": cfg.get("ai_enabled", True),
    }


def save_ai_config(db: Session, data: dict[str, Any]) -> dict[str, Any]:
    """写入 AI 配置到数据库（只更新传入的 key）"""
    ensure_ai_config_table(db)
    for key, value in data.items():
        if key not in _AI_CONFIG_DEFAULTS:
            continue
        str_value = str(value) if value is not None else ""
        existing = db.execute(
            text("SELECT id FROM ai_config WHERE config_key = :key"),
            {"key": key},
        ).mappings().first()
        if existing:
            db.execute(
                text("UPDATE ai_config SET config_value = :val WHERE config_key = :key"),
                {"key": key, "val": str_value},
            )
        else:
            db.execute(
                text("INSERT INTO ai_config (config_key, config_value) VALUES (:key, :val)"),
                {"key": key, "val": str_value},
            )
    db.commit()
    return get_ai_config(db)


def mask_api_key(key: str) -> str:
    """对 API Key 脱敏显示"""
    if not key or len(key) <= 8:
        return "*" * len(key) if key else ""
    return f"{key[:4]}****{key[-4:]}"
