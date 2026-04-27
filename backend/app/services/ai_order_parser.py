import base64
import json
import logging
import re
import time
from pathlib import Path
from typing import Any, Optional

import httpx
from sqlalchemy.orm import Session

from app.config import settings
from app.services.ai_config import log_ai_call

logger = logging.getLogger(__name__)


class AIOrderParserError(Exception):
    pass


# ==========================================================================
# 智能体 1 — 报货验证 Agent（判断是否为报货 + 信息是否完整）
# ==========================================================================
ORDER_VALIDATOR_SYSTEM_PROMPT = """你是一个服装行业报货信息验证助手。
你的唯一任务是判断客户发来的内容（文字、图片、表格）是否包含实际的报货/下单数据。

完整的报货信息需要四个要素：款号（货号）、颜色、尺码、对应数量。

判断规则（按优先级执行）：

【情况1 → is_order=false】内容没有任何实际报货数据：
- 只说了"报单"、"下单"、"报货"、"我要下单"等意图词，但没有任何款号、颜色、尺码、数量
- 日常聊天、打招呼、问候、表情包、闲聊图片、讨论非订单话题
- 只是在问价格、问款式、咨询但没有具体下单数据
→ 这些都不算报货信息，返回 is_order=false

【情况2 → is_order=true, is_complete=false】内容包含部分报货数据但不完整：
- 有款号但缺颜色/尺码/数量（如"A1234 要10件"→ 缺颜色和尺码）
- 有款号和颜色但缺尺码或数量（如"A1234 黑色"→ 缺尺码和数量）
- 有数量但缺款号（如"红色 S码 20件"→ 缺款号）
- 图片/表格中能看到部分订单信息但缺少某些列
→ 返回 is_order=true, is_complete=false，在 missing_fields 中精确列出缺少的要素

【情况3 → is_order=true, is_complete=true】内容包含完整报货数据：
- 文字中同时包含款号、颜色、尺码、数量（如"A1234 黑色 S码 10件 M码 5件"）
- 图片中能看到完整的订单表格（含款号、颜色、尺码、数量列）
- Excel 摘要中能看到完整的款号、颜色、尺码、数量数据
→ 返回 is_order=true, is_complete=true

missing_fields 只能包含这四个值：款号、颜色、尺码、数量

严格只返回 JSON，不要返回 markdown：
{
  "is_order": true/false,
  "is_complete": true/false,
  "missing_fields": ["颜色", "尺码"],
  "reason": "简短说明判断依据"
}
"""

# ==========================================================================
# 智能体 2 — 订单解析 Agent（将报货内容解析为结构化 JSON）
# ==========================================================================
ORDER_PARSER_SYSTEM_PROMPT = """你是一个服装订单解析助手。请把客户通过企微发送的文本、图片、表格内容解析成结构化订单 JSON。
要求：
1. 尽可能识别客户名、联系人、备注、下单日期。
2. items 中每个款号单独成行，并识别颜色、尺码数量。
3. 如果信息不确定，保留在 uncertainties 数组中，不要编造。
4. 严格返回 JSON，不要返回 markdown。
返回结构：
{
  "customer_name": "",
  "contact_person": "",
  "order_date": "YYYY-MM-DD",
  "remark": "",
  "items": [
    {
      "product_no": "",
      "product_name": "",
      "color": "",
      "brand": "",
      "unit": "件",
      "price": 0,
      "discount": 1,
      "sizes": [
        {"size": "S", "qty": 1}
      ],
      "remark": ""
    }
  ],
  "uncertainties": []
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

    async def upload_file(self, file_bytes: bytes, filename: str, model: str, db: Optional[Session] = None) -> str:
        """上传文件到千问临时存储，返回 oss:// URL（有48小时有效期）"""
        cfg = self._load_config(db)
        self._ensure_enabled(cfg)
        api_key = cfg["api_key"]

        async with httpx.AsyncClient(timeout=60) as client:
            # 步骤1: 获取上传凭证
            policy_resp = await client.get(
                "https://dashscope.aliyuncs.com/api/v1/uploads",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                params={"action": "getPolicy", "model": model},
            )
            policy_resp.raise_for_status()
            policy_data = policy_resp.json()["data"]

            # 步骤2: 上传文件到 OSS
            key = f"{policy_data['upload_dir']}/{filename}"
            upload_resp = await client.post(
                policy_data["upload_host"],
                data={
                    "OSSAccessKeyId": policy_data["oss_access_key_id"],
                    "Signature": policy_data["signature"],
                    "policy": policy_data["policy"],
                    "x-oss-object-acl": policy_data["x_oss_object_acl"],
                    "x-oss-forbid-overwrite": policy_data["x_oss_forbid_overwrite"],
                    "key": key,
                    "success_action_status": "200",
                },
                files={"file": (filename, file_bytes)},
            )
            upload_resp.raise_for_status()

        oss_url = f"oss://{key}"
        logger.info("文件上传成功: %s -> %s", filename, oss_url)
        return oss_url

    @staticmethod
    def _messages_contain_oss(messages: list[dict[str, Any]]) -> bool:
        """检测 messages 中是否包含 oss:// URL"""
        for msg in messages:
            content = msg.get("content")
            if isinstance(content, str) and "oss://" in content:
                return True
            if isinstance(content, list):
                for part in content:
                    url = (part.get("image_url") or {}).get("url") or ""
                    if url.startswith("oss://"):
                        return True
        return False

    async def _chat(self, model: str, messages: list[dict[str, Any]], db: Optional[Session] = None, caller: str = "") -> dict[str, Any]:
        cfg = self._load_config(db)
        self._ensure_enabled(cfg)
        base_url = cfg["base_url"].rstrip("/")
        api_key = cfg["api_key"]
        temperature = cfg.get("temperature", 0.1)

        request_body: dict[str, Any] = {
            "model": model,
            "temperature": temperature,
            "response_format": {"type": "json_object"},
            "messages": messages,
        }

        headers: dict[str, str] = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        if self._messages_contain_oss(messages):
            headers["X-DashScope-OssResourceResolve"] = "enable"

        # 构建请求摘要
        req_summary = self._build_request_summary(messages)

        t0 = time.time()
        try:
            async with httpx.AsyncClient(timeout=120) as client:
                response = await client.post(
                    f"{base_url}/chat/completions",
                    headers=headers,
                    json=request_body,
                )
            response.raise_for_status()
            payload = response.json()
            duration_ms = int((time.time() - t0) * 1000)

            usage = payload.get("usage") or {}
            content = (((payload.get("choices") or [{}])[0].get("message") or {}).get("content") or "{}").strip()

            # 记录日志
            if db is not None:
                log_ai_call(
                    db,
                    model=model,
                    caller=caller or "ai_order_parser",
                    prompt_tokens=usage.get("prompt_tokens", 0),
                    completion_tokens=usage.get("completion_tokens", 0),
                    total_tokens=usage.get("total_tokens", 0),
                    duration_ms=duration_ms,
                    status="success",
                    request_summary=req_summary,
                    response_summary=content[:2000],
                )

            return self._extract_json(content)
        except Exception as exc:
            duration_ms = int((time.time() - t0) * 1000)
            if db is not None:
                log_ai_call(
                    db,
                    model=model,
                    caller=caller or "ai_order_parser",
                    duration_ms=duration_ms,
                    status="error",
                    error_message=str(exc)[:2000],
                    request_summary=req_summary,
                )
            raise

    @staticmethod
    def _build_request_summary(messages: list[dict[str, Any]]) -> str:
        """构建请求摘要（仅提取文本部分，忽略 base64/图片）"""
        parts = []
        for msg in messages:
            role = msg.get("role", "")
            content = msg.get("content")
            if isinstance(content, str):
                parts.append(f"[{role}] {content[:300]}")
            elif isinstance(content, list):
                texts = [p.get("text", "") for p in content if p.get("type") == "text"]
                combined = " ".join(texts)[:300]
                has_img = any(p.get("type") == "image_url" for p in content)
                suffix = " [+图片]" if has_img else ""
                parts.append(f"[{role}] {combined}{suffix}")
        return "\n".join(parts)[:2000]

    # ------------------------------------------------------------------
    # 智能体 1：报货验证 — 判断内容是否为报货 + 信息完整性
    # ------------------------------------------------------------------
    def _build_multimodal_parts(
        self, context_messages: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """将统一消息列表转为 OpenAI 多模态 content parts"""
        parts: list[dict[str, Any]] = []
        for idx, msg in enumerate(context_messages, 1):
            msg_type = msg.get("type", "text")
            if msg_type == "text":
                parts.append({"type": "text", "text": f"[消息{idx}] {msg.get('content', '')}"})
            elif msg_type == "image":
                if msg.get("oss_url"):
                    parts.append({"type": "text", "text": f"[消息{idx}] 图片:"})
                    parts.append({"type": "image_url", "image_url": {"url": msg["oss_url"]}})
                elif msg.get("base64"):
                    mime = msg.get("mime") or "image/png"
                    parts.append({"type": "text", "text": f"[消息{idx}] 图片:"})
                    parts.append({"type": "image_url", "image_url": {"url": f"data:{mime};base64,{msg['base64']}"}})
            elif msg_type == "file":
                summary = msg.get("excel_summary") or msg.get("content") or ""
                fname = msg.get("file_name") or "附件"
                parts.append({"type": "text", "text": f"[消息{idx}] 文件 {fname}:\n{summary}"})
        return parts

    async def validate_order(
        self,
        context_messages: list[dict[str, Any]],
        db: Optional[Session] = None,
    ) -> dict[str, Any]:
        """智能体1: 验证消息是否为报货信息及完整性。

        返回:
            {
                "is_order": bool,
                "is_complete": bool,
                "missing_fields": ["颜色", ...],
                "reason": "..."
            }
        """
        cfg = self._load_config(db)
        has_image = any(m.get("type") == "image" for m in context_messages)
        model = cfg["vision_model"] if has_image else cfg["model"]

        user_parts = self._build_multimodal_parts(context_messages)
        if not user_parts:
            return {"is_order": False, "is_complete": False, "missing_fields": [], "reason": "无内容"}

        user_content: Any = user_parts if len(user_parts) > 1 else user_parts[0].get("text", "")

        try:
            result = await self._chat(
                model,
                [
                    {"role": "system", "content": ORDER_VALIDATOR_SYSTEM_PROMPT},
                    {"role": "user", "content": user_content},
                ],
                db=db,
                caller="validate_order",
            )
            return {
                "is_order": bool(result.get("is_order", False)),
                "is_complete": bool(result.get("is_complete", False)),
                "missing_fields": list(result.get("missing_fields") or []),
                "reason": str(result.get("reason", "")),
            }
        except Exception as exc:
            logger.warning("智能体1(验证)失败: %s", exc)
            return {"is_order": False, "is_complete": False, "missing_fields": [], "reason": f"验证异常: {exc}"}

    # 向后兼容：pre_judge → validate_order
    async def pre_judge(
        self,
        context_messages: list[dict[str, Any]],
        db: Optional[Session] = None,
    ) -> dict[str, Any]:
        return await self.validate_order(context_messages, db=db)

    # ------------------------------------------------------------------
    # 智能体 2：订单解析 — 将内容解析为结构化 JSON
    # ------------------------------------------------------------------
    async def parse_text(self, text: str, customer_hint: str = "", db: Optional[Session] = None) -> dict[str, Any]:
        cfg = self._load_config(db)
        return await self._chat(
            cfg["model"],
            [
                {"role": "system", "content": ORDER_PARSER_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": f"客户提示: {customer_hint or '无'}\n原始文本:\n{text}",
                },
            ],
            db=db,
            caller="parse_text",
        )

    async def parse_image_base64(self, image_base64: str, mime_type: str = "image/png", extra_text: str = "", db: Optional[Session] = None) -> dict[str, Any]:
        cfg = self._load_config(db)
        return await self._chat(
            cfg["vision_model"],
            [
                {"role": "system", "content": ORDER_PARSER_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": f"请解析图片中的下单信息。补充说明: {extra_text or '无'}"},
                        {"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{image_base64}"}},
                    ],
                },
            ],
            db=db,
            caller="parse_image",
        )

    async def parse_excel_summary(self, file_name: str, text_summary: str, customer_hint: str = "", db: Optional[Session] = None) -> dict[str, Any]:
        cfg = self._load_config(db)
        return await self._chat(
            cfg["model"],
            [
                {"role": "system", "content": ORDER_PARSER_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": f"文件名: {file_name}\n客户提示: {customer_hint or '无'}\n表格摘要:\n{text_summary}",
                },
            ],
            db=db,
            caller="parse_excel",
        )

    async def parse_batch(
        self,
        context_messages: list[dict[str, Any]],
        customer_hint: str = "",
        db: Optional[Session] = None,
    ) -> dict[str, Any]:
        """智能体2: 批量解析多条消息为结构化订单 JSON。

        context_messages 每项结构:
        {
            "type": "text" | "image" | "file",
            "content": "文字内容",
            "base64": "...",
            "mime": "image/png",
            "oss_url": "oss://...",
            "file_name": "订单.xlsx",
            "excel_summary": "表格摘要文本",
        }
        """
        cfg = self._load_config(db)
        has_image = any(m.get("type") == "image" for m in context_messages)
        model = cfg["vision_model"] if has_image else cfg["model"]

        user_parts: list[dict[str, Any]] = []
        user_parts.append({"type": "text", "text": f"客户提示: {customer_hint or '无'}\n以下是客户在群聊中发的下单相关消息，请合并解析为一个完整订单："})

        for idx, msg in enumerate(context_messages, 1):
            msg_type = msg.get("type", "text")
            sender = msg.get("sender_name") or ""
            sender_tag = f"({sender})" if sender else ""
            if msg_type == "text":
                user_parts.append({"type": "text", "text": f"[消息{idx}]{sender_tag} {msg.get('content', '')}"})
            elif msg_type == "image":
                if msg.get("oss_url"):
                    user_parts.append({"type": "text", "text": f"[消息{idx}]{sender_tag} 图片:"})
                    user_parts.append({"type": "image_url", "image_url": {"url": msg["oss_url"]}})
                elif msg.get("base64"):
                    mime = msg.get("mime") or "image/png"
                    user_parts.append({"type": "text", "text": f"[消息{idx}]{sender_tag} 图片:"})
                    user_parts.append({"type": "image_url", "image_url": {"url": f"data:{mime};base64,{msg['base64']}"}})
            elif msg_type == "file":
                summary = msg.get("excel_summary") or msg.get("content") or ""
                fname = msg.get("file_name") or "附件"
                user_parts.append({"type": "text", "text": f"[消息{idx}]{sender_tag} 文件 {fname}:\n{summary}"})

        return await self._chat(
            model,
            [
                {"role": "system", "content": ORDER_PARSER_SYSTEM_PROMPT},
                {"role": "user", "content": user_parts},
            ],
            db=db,
            caller="parse_batch",
        )



ai_order_parser = AIOrderParser()
