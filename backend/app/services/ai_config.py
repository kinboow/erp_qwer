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

_DDL_AI_CALL_LOGS = """
CREATE TABLE IF NOT EXISTS ai_call_logs (
    id              BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    called_at       DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '调用时间',
    model           VARCHAR(200) NOT NULL DEFAULT '' COMMENT '模型名称',
    caller          VARCHAR(200) NOT NULL DEFAULT '' COMMENT '调用来源',
    prompt_tokens   INT UNSIGNED DEFAULT 0 COMMENT 'prompt token 数',
    completion_tokens INT UNSIGNED DEFAULT 0 COMMENT 'completion token 数',
    total_tokens    INT UNSIGNED DEFAULT 0 COMMENT '总 token 数',
    duration_ms     INT UNSIGNED DEFAULT 0 COMMENT '耗时(毫秒)',
    status          VARCHAR(20) NOT NULL DEFAULT 'success' COMMENT 'success/error',
    error_message   TEXT NULL COMMENT '错误信息',
    request_summary TEXT NULL COMMENT '请求摘要',
    response_summary TEXT NULL COMMENT '响应摘要',
    INDEX idx_called_at (called_at),
    INDEX idx_caller (caller),
    INDEX idx_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
"""

# 供应商预设配置
AI_PROVIDER_PRESETS: dict[str, dict[str, str]] = {
    "qwen": {
        "label": "通义千问（阿里云）",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "default_model": "qwen3.5-flash",
        "default_vision_model": "qwen3.5-flash",
    },
    "bytedance": {
        "label": "豆包（字节跳动 · 火山方舟）",
        "base_url": "https://ark.cn-beijing.volces.com/api/v3",
        "default_model": "doubao-seed-2-0-lite-260215",
        "default_vision_model": "doubao-seed-2-0-lite-260215",
    },
    "custom": {
        "label": "自定义（OpenAI 兼容）",
        "base_url": "",
        "default_model": "",
        "default_vision_model": "",
    },
}

_AI_CONFIG_DEFAULTS: dict[str, str] = {
    "ai_provider": "qwen",
    "ai_base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
    "ai_api_key": "",
    "ai_model": "qwen3.5-flash",
    "ai_vision_model": "qwen3.5-flash",
    "ai_temperature": "0.1",
    "ai_enabled": "true",
}


def ensure_ai_config_table(db: Session) -> None:
    db.execute(text(_DDL_AI_CONFIG))
    db.execute(text(_DDL_AI_CALL_LOGS))
    db.commit()


def log_ai_call(
    db: Session,
    *,
    model: str = "",
    caller: str = "",
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    total_tokens: int = 0,
    duration_ms: int = 0,
    status: str = "success",
    error_message: str = "",
    request_summary: str = "",
    response_summary: str = "",
) -> None:
    """记录一次 AI 调用日志到数据库"""
    try:
        db.execute(text(
            "INSERT INTO ai_call_logs "
            "(model, caller, prompt_tokens, completion_tokens, total_tokens, duration_ms, status, error_message, request_summary, response_summary) "
            "VALUES (:model, :caller, :pt, :ct, :tt, :dur, :status, :err, :req, :resp)"
        ), {
            "model": model[:200],
            "caller": caller[:200],
            "pt": prompt_tokens,
            "ct": completion_tokens,
            "tt": total_tokens,
            "dur": duration_ms,
            "status": status[:20],
            "err": error_message[:2000] if error_message else None,
            "req": request_summary[:2000] if request_summary else None,
            "resp": response_summary[:2000] if response_summary else None,
        })
        db.commit()
    except Exception as exc:
        logger.warning("写入 AI 调用日志失败: %s", exc)


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
        "provider": (cfg.get("ai_provider") or "").strip() or "qwen",
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
