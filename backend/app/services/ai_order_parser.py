import base64
import json
import logging
import re
from typing import Any, Optional

import httpx
from sqlalchemy.orm import Session

from app.config import settings

logger = logging.getLogger(__name__)


class AIOrderParserError(Exception):
    pass


ORDER_PARSE_SYSTEM_PROMPT = """你是一个服装订单解析助手。请把客户通过企微发送的文本、图片、表格内容解析成结构化订单 JSON。
要求：
1. 尽可能识别客户名、联系人、备注、下单日期。
2. items 中每个款号单独成行，并识别颜色、尺码数量。
3. 如果信息不确定，保留在 uncertainties 数组中，不要编造。
4. 严格返回 JSON，不要返回 markdown。
返回结构：
{
  \"customer_name\": \"\",
  \"contact_person\": \"\",
  \"order_date\": \"YYYY-MM-DD\",
  \"remark\": \"\",
  \"items\": [
    {
      \"product_no\": \"\",
      \"product_name\": \"\",
      \"color\": \"\",
      \"brand\": \"\",
      \"unit\": \"件\",
      \"price\": 0,
      \"discount\": 1,
      \"sizes\": [
        {\"size\": \"S\", \"qty\": 1}
      ],
      \"remark\": \"\"
    }
  ],
  \"uncertainties\": []
}
"""


class AIOrderParser:
    def __init__(self) -> None:
        # .env 回退默认值
        self._fallback_base_url = settings.OPENAI_BASE_URL.rstrip("/")
        self._fallback_api_key = settings.OPENAI_API_KEY
        self._fallback_model = settings.OPENAI_MODEL
        self._fallback_vision_model = settings.OPENAI_VISION_MODEL

    # ------------------------------------------------------------------
    # 配置加载（DB 优先，.env 回退）
    # ------------------------------------------------------------------
    def _load_config(self, db: Optional[Session] = None) -> dict[str, Any]:
        if db is not None:
            try:
                from app.services.ai_config import get_ai_config_for_parser
                return get_ai_config_for_parser(db)
            except Exception as exc:
                logger.warning("从数据库加载 AI 配置失败，回退到 .env: %s", exc)
        return {
            "base_url": self._fallback_base_url,
            "api_key": self._fallback_api_key,
            "model": self._fallback_model,
            "vision_model": self._fallback_vision_model,
            "temperature": 0.1,
            "enabled": True,
        }

    def _ensure_enabled(self, cfg: dict[str, Any]):
        if not cfg.get("enabled", True):
            raise AIOrderParserError("AI 解析已在后台配置中关闭")
        if not cfg.get("api_key"):
            raise AIOrderParserError("未配置 AI API Key，无法进行 AI 解析")

    @staticmethod
    def _extract_json(text_content: str) -> dict[str, Any]:
        """从 AI 返回的文本中提取 JSON（兼容 markdown 代码块包裹）"""
        text_content = text_content.strip()
        # 1. 直接尝试解析
        try:
            return json.loads(text_content)
        except Exception:
            pass
        # 2. 尝试从 ```json ... ``` 代码块中提取
        m = re.search(r"```(?:json)?\s*\n?(\{.*?\})\s*```", text_content, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(1))
            except Exception:
                pass
        # 3. 尝试提取第一个 { ... } 块
        m = re.search(r"(\{.*\})", text_content, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(1))
            except Exception:
                pass
        raise AIOrderParserError(f"AI 返回内容不是有效 JSON: {text_content[:300]}")

    async def _chat(self, model: str, messages: list[dict[str, Any]], db: Optional[Session] = None) -> dict[str, Any]:
        cfg = self._load_config(db)
        self._ensure_enabled(cfg)
        base_url = cfg["base_url"].rstrip("/")
        api_key = cfg["api_key"]
        temperature = cfg.get("temperature", 0.1)

        request_body: dict[str, Any] = {
            "model": model,
            "temperature": temperature,
            "messages": messages,
        }

        async with httpx.AsyncClient(timeout=120) as client:
            response = await client.post(
                f"{base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json=request_body,
            )
        response.raise_for_status()
        payload = response.json()
        content = (((payload.get("choices") or [{}])[0].get("message") or {}).get("content") or "{}").strip()
        return self._extract_json(content)

    async def parse_text(self, text: str, customer_hint: str = "", db: Optional[Session] = None) -> dict[str, Any]:
        cfg = self._load_config(db)
        return await self._chat(
            cfg["model"],
            [
                {"role": "system", "content": ORDER_PARSE_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": f"客户提示: {customer_hint or '无'}\n原始文本:\n{text}",
                },
            ],
            db=db,
        )

    async def parse_image_base64(self, image_base64: str, mime_type: str = "image/png", extra_text: str = "", db: Optional[Session] = None) -> dict[str, Any]:
        cfg = self._load_config(db)
        return await self._chat(
            cfg["vision_model"],
            [
                {"role": "system", "content": ORDER_PARSE_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": f"请解析图片中的下单信息。补充说明: {extra_text or '无'}"},
                        {"type": "image_url", "image_url": {"url": image_base64}},
                    ],
                },
            ],
            db=db,
        )

    async def parse_excel_summary(self, file_name: str, text_summary: str, customer_hint: str = "", db: Optional[Session] = None) -> dict[str, Any]:
        cfg = self._load_config(db)
        return await self._chat(
            cfg["model"],
            [
                {"role": "system", "content": ORDER_PARSE_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": f"文件名: {file_name}\n客户提示: {customer_hint or '无'}\n表格摘要:\n{text_summary}",
                },
            ],
            db=db,
        )

    async def parse_batch(
        self,
        context_messages: list[dict[str, Any]],
        customer_hint: str = "",
        db: Optional[Session] = None,
    ) -> dict[str, Any]:
        """批量解析多条上下文消息（文字+图片混合），用于 @机器人 场景。

        context_messages 每项结构:
        {
            "type": "text" | "image" | "file",
            "content": "文字内容",               # type=text 时
            "base64": "...",                     # type=image 时
            "mime": "image/png",                  # type=image 时
            "file_name": "订单.xlsx",             # type=file 时
            "excel_summary": "表格摘要文本",       # type=file 时（已预处理）
        }
        """
        cfg = self._load_config(db)
        has_image = any(m.get("type") == "image" for m in context_messages)
        model = cfg["vision_model"] if has_image else cfg["model"]

        # 构造多模态 user content
        user_parts: list[dict[str, Any]] = []
        user_parts.append({"type": "text", "text": f"客户提示: {customer_hint or '无'}\n以下是客户在群聊中发的下单相关消息，请合并解析为一个完整订单："})

        for idx, msg in enumerate(context_messages, 1):
            msg_type = msg.get("type", "text")
            if msg_type == "text":
                user_parts.append({"type": "text", "text": f"[消息{idx}] {msg.get('content', '')}"})
            elif msg_type == "image" and msg.get("base64"):
                mime = msg.get("mime") or "image/png"
                user_parts.append({"type": "text", "text": f"[消息{idx}] 图片:"})
                user_parts.append({"type": "image_url", "image_url": {"url": msg['base64']}})
            elif msg_type == "file":
                summary = msg.get("excel_summary") or msg.get("content") or ""
                fname = msg.get("file_name") or "附件"
                user_parts.append({"type": "text", "text": f"[消息{idx}] 文件 {fname}:\n{summary}"})

        return await self._chat(
            model,
            [
                {"role": "system", "content": ORDER_PARSE_SYSTEM_PROMPT},
                {"role": "user", "content": user_parts},
            ],
            db=db,
        )


    async def upload_file(self, file_bytes: bytes, filename: str, purpose: str = "agent", db: Optional[Session] = None) -> dict[str, Any]:
        """上传文件到智谱 /files API，返回 FileObject"""
        cfg = self._load_config(db)
        self._ensure_enabled(cfg)
        base_url = cfg["base_url"].rstrip("/")
        api_key = cfg["api_key"]

        async with httpx.AsyncClient(timeout=120) as client:
            response = await client.post(
                f"{base_url}/files",
                headers={"Authorization": f"Bearer {api_key}"},
                files={"file": (filename, file_bytes)},
                data={"purpose": purpose},
            )
        response.raise_for_status()
        return response.json()


ai_order_parser = AIOrderParser()
