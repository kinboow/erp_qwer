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
            "provider": "qwen",
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

    def supports_oss_upload(self, db: Optional[Session] = None) -> bool:
        """当前供应商是否支持 DashScope OSS 上传（仅通义千问支持）"""
        cfg = self._load_config(db)
        return cfg.get("provider", "qwen") == "qwen"

    async def upload_file(self, file_bytes: bytes, filename: str, model: str, db: Optional[Session] = None) -> str:
        """上传文件到千问临时存储，返回 oss:// URL（有48小时有效期）。
        注意：仅通义千问（DashScope）支持此功能，其他供应商请使用 base64 传图。
        """
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

        provider = cfg.get("provider", "qwen")
        request_body: dict[str, Any] = {
            "model": model,
            "temperature": temperature,
            "messages": messages,
        }
        # response_format json_object 仅部分供应商/模型支持
        if provider == "qwen":
            request_body["response_format"] = {"type": "json_object"}
        # 字节跳动豆包模型开启深度思考
        if provider == "bytedance":
            request_body["thinking"] = {"type": "enabled"}

        headers: dict[str, str] = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        if self._messages_contain_oss(messages) and cfg.get("provider", "qwen") == "qwen":
            headers["X-DashScope-OssResourceResolve"] = "enable"

        # 构建请求摘要
        req_summary = self._build_request_summary(messages)

        # 深度思考模型需要更长超时
        timeout = 240 if provider == "bytedance" else 180

        t0 = time.time()
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(
                    f"{base_url}/chat/completions",
                    headers=headers,
                    json=request_body,
                )
            if response.status_code >= 400:
                error_body = response.text
                logger.error("AI API 请求失败 [%s %s]: status=%d body=%s",
                             provider, model, response.status_code, error_body[:1000])
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
                    error_message=f"{type(exc).__name__}: {exc}"[:2000],
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

    # ------------------------------------------------------------------
    # 智能体 A：款号提取 + 图片旋转角度判断
    # ------------------------------------------------------------------
    async def extract_product_nos(
        self,
        context_messages: list[dict[str, Any]],
        db: Optional[Session] = None,
        catalog: Optional[list[dict[str, Any]]] = None,
    ) -> dict[str, Any]:
        """智能体A: 从本年产品目录中匹配款号，并判断图片旋转角度。

        Args:
            catalog: 本年产品目录列表，由 query_current_year_catalog() 返回。
                     如果为 None 则降级为无目录模式。

        返回: {"product_nos": ["1234", "5678"], "rotation_angle": 0}
        """
        cfg = self._load_config(db)
        has_image = any(m.get("type") == "image" for m in context_messages)
        model = cfg["vision_model"] if has_image else cfg["model"]

        user_parts = self._build_multimodal_parts(context_messages)
        if not user_parts:
            return {"product_nos": [], "rotation_angle": 0}

        user_content: Any = user_parts if len(user_parts) > 1 else user_parts[0].get("text", "")

        # 根据是否有目录选择提示词
        if catalog is not None:
            catalog_text = _build_catalog_text(catalog)
            system_prompt = _PRODUCT_NO_EXTRACT_PROMPT_TEMPLATE.format(catalog_text=catalog_text)
        else:
            system_prompt = PRODUCT_NO_EXTRACT_SYSTEM_PROMPT

        try:
            result = await self._chat(
                model,
                [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content},
                ],
                db=db,
                caller="extract_product_nos",
            )
            nos = result.get("product_nos") or []
            filtered_nos = [str(n).strip() for n in nos if str(n).strip().isdigit()]
            # 旋转角度：正数=顺时针，负数=逆时针，只接受 ±90/±180/±270
            try:
                angle = int(result.get("rotation_angle") or 0)
            except (ValueError, TypeError):
                angle = 0
            if angle not in (0, 90, -90, 180, -180, 270, -270):
                angle = 0
            return {"product_nos": filtered_nos, "rotation_angle": angle}
        except Exception as exc:
            logger.warning("智能体A(款号提取)失败: %s", exc)
            return {"product_nos": [], "rotation_angle": 0}

    async def extract_product_nos_from_text(
        self, text_content: str, db: Optional[Session] = None,
    ) -> list[str]:
        """从纯文本中提取款号的便捷方法"""
        result = await self.extract_product_nos(
            [{"type": "text", "content": text_content}], db=db,
        )
        return result.get("product_nos") or []

    async def extract_product_nos_from_image(
        self, image_base64: str, mime_type: str = "image/png",
        extra_text: str = "", db: Optional[Session] = None,
    ) -> list[str]:
        """从图片中提取款号的便捷方法"""
        msgs: list[dict[str, Any]] = [{"type": "image", "base64": image_base64, "mime": mime_type}]
        if extra_text:
            msgs.insert(0, {"type": "text", "content": extra_text})
        result = await self.extract_product_nos(msgs, db=db)
        return result.get("product_nos") or []

    async def extract_product_nos_from_excel(
        self, file_name: str, text_summary: str, db: Optional[Session] = None,
    ) -> list[str]:
        """从 Excel 摘要中提取款号的便捷方法"""
        result = await self.extract_product_nos(
            [{"type": "text", "content": f"文件名: {file_name}\n表格摘要:\n{text_summary}"}],
            db=db,
        )
        return result.get("product_nos") or []

    # ------------------------------------------------------------------
    # 智能体 B：带库存上下文的详细解析
    # ------------------------------------------------------------------
    async def parse_with_product_context(
        self,
        context_messages: list[dict[str, Any]],
        product_context_data: dict[str, Any],
        customer_hint: str = "",
        db: Optional[Session] = None,
    ) -> dict[str, Any]:
        """智能体B: 带库存可选颜色/尺码上下文解析完整订单。

        Args:
            context_messages: 统一消息列表
            product_context_data: {"sizes": [...], "colors": [...], "mappings": {...}}
            customer_hint: 客户名称提示
        """
        cfg = self._load_config(db)
        has_image = any(m.get("type") == "image" for m in context_messages)
        model = cfg["vision_model"] if has_image else cfg["model"]

        # 动态构建系统提示词
        system_prompt = build_context_parser_prompt(
            sizes=product_context_data.get("sizes") or [],
            colors=product_context_data.get("colors") or [],
            mappings=product_context_data.get("mappings") or {},
        )

        # 构建用户消息：仅 "解析内容" + 图片，不附加多余文本
        user_parts: list[dict[str, Any]] = [{"type": "text", "text": "解析内容"}]
        for msg in context_messages:
            if msg.get("type") == "image":
                if msg.get("oss_url"):
                    user_parts.append({"type": "image_url", "image_url": {"url": msg["oss_url"]}})
                elif msg.get("base64"):
                    mime = msg.get("mime") or "image/png"
                    user_parts.append({"type": "image_url", "image_url": {"url": f"data:{mime};base64,{msg['base64']}"}})
        if len(user_parts) == 1 and not any(m.get("type") == "image" for m in context_messages):
            return {"style_code": None, "original_style_code": None, "inventory": [], "remarks": "无图片内容"}

        user_content: Any = user_parts

        raw_result = await self._chat(
            model,
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            db=db,
            caller="parse_with_context",
        )
        return convert_inventory_result_to_standard(raw_result)


# ==========================================================================
# 智能体 A — 款号提取 Agent（从本年产品目录中匹配款号）
# ==========================================================================
_PRODUCT_NO_EXTRACT_PROMPT_TEMPLATE = """你是一个服装行业款号匹配助手。
你有两个任务：

任务1：从客户发来的内容（文字、图片、表格）中识别出提到的款号（货号），然后**严格从下方的【本年产品目录】中匹配**。

任务2：如果输入包含图片，判断图片中的纸张/内容需要顺时针旋转多少度才能变成正向可读（文字从左到右、从上到下）。

【本年产品目录】
{catalog_text}

款号匹配规则：
1. 客户内容中出现的数字、名称，需要与上方【本年产品目录】中的 product_no 或别名(aliases) 进行匹配
2. **只能输出目录中存在的 product_no**，绝对禁止编造不在目录中的款号
3. 如果客户写的是别名（aliases 中的值），请输出该别名对应的 product_no
4. 不要把价格、数量、尺码、日期等数字误认为款号
5. 如果内容中出现类似"款号"、"货号"、"款"等关键词后面的数字，优先尝试匹配
6. 同一个 product_no 只输出一次，去重
7. 如果客户提到的款号在目录中完全找不到匹配，不要输出该款号
8. 如果完全没有匹配到任何款号，返回空数组

图片旋转判断规则：
1. 观察图片中手写文字/表格的朝向
2. 判断需要旋转多少度才能让内容变成正向可读（文字从左到右、从上到下）
3. rotation_angle 用正负数表示方向：正数=顺时针旋转，负数=逆时针旋转
4. 只能是以下值之一：0, 90, -90, 180, -180, 270, -270
5. 0 表示图片已经是正的，不需要旋转
6. 例如：文字头朝左 → 需要顺时针旋转90度 → 填 90；文字头朝右 → 需要逆时针旋转90度 → 填 -90
7. 如果没有图片或无法判断，填 0

严格只返回 JSON，不要返回 markdown：
{{
  "product_nos": ["1234", "5678"],
  "rotation_angle": 0,
  "reason": "简短说明匹配依据和旋转判断"
}}
"""


def _build_catalog_text(catalog: list[dict[str, Any]]) -> str:
    """将产品目录列表格式化为提示词文本。"""
    if not catalog:
        return "（目录为空）"
    lines: list[str] = []
    for item in catalog:
        pno = item.get("product_no", "")
        pname = item.get("product_name", "")
        aliases = item.get("aliases") or []
        alias_str = f"  别名: {', '.join(aliases)}" if aliases else ""
        lines.append(f"- {pno}  {pname}{alias_str}")
    return "\n".join(lines)


# 向后兼容：无目录时的降级提示词
PRODUCT_NO_EXTRACT_SYSTEM_PROMPT = _PRODUCT_NO_EXTRACT_PROMPT_TEMPLATE.replace("{catalog_text}", "（无目录信息，请尽可能从内容中提取纯数字款号）")

# ==========================================================================
# 智能体 B — 带库存上下文的详细解析 Agent（动态提示词模板）
# ==========================================================================
_CONTEXT_PARSER_PROMPT_TEMPLATE = """【⚠️ 固定配置】
1. 可选尺码列表：{sizes_list}
2. 可选颜色列表：{colors_list}
3. 款号映射关系：{style_mapping}

【核心执行规则（AI必须100%严格遵守，不得修改）】
1. 图片解析核心要求
你是专业的手写服装库存数据解析工具，仅识别图片中与服装款号、颜色、尺码、对应数量相关的手写内容，其余无关信息全部忽略。针对手写内容，优先做语义精准匹配，所有识别结果必须严格限定在上方填写的可选尺码、可选颜色范围内，超出范围的内容直接丢弃，绝对禁止编造、臆造任何不在可选列表里的颜色、尺码、数量。

2. 多颜色多尺码适配规则
- 无论图片中有多少个颜色、单个颜色对应多少个尺码，都必须先匹配【可选颜色列表】中的标准颜色名称，手写简写/俗称必须对应到列表内的标准名（如手写"黑"匹配列表内的"黑色"，手写"茶"匹配列表内的"茶色"），无法匹配的颜色直接丢弃。
- 每个匹配到的有效颜色，必须单独生成一条库存记录；单条颜色记录下的size_stock对象，必须完整包含【可选尺码列表】里的**全部尺码**，识别到有效数量的填对应阿拉伯数字，无标注、无法识别、未匹配到的尺码，统一填0，不允许遗漏任何可选尺码，也不允许出现列表外的尺码。

3. 款号映射转换规则（极其重要）
- 先识别图片中的原始手写款号，再严格按照【款号映射关系】做一对一转换，原始款号完全匹配映射键的，输出对应目标款号。
- 若识别到的原始款号不在映射关系中，说明该款号不属于当前供应商，必须完全忽略该款号及其对应的所有颜色、尺码、数量信息，不要输出到结果中。
- 图片中可能同时包含多个供应商的款号信息，你只需要解析在【款号映射关系】中能匹配到的款号，其余全部忽略。
- 如果图片中所有款号都不在映射关系中，inventory返回空数组，remarks标注“图片中的款号均不在当前供应商的款号映射中”。

4. 异常处理规则
- 手写内容模糊、涂改、无法辨认的数量，统一填0。
- 识别到的颜色/尺码无法匹配到可选列表的，直接丢弃该条内容，不纳入最终结果。
- 未识别到任何有效库存数据的，inventory为空数组，remarks标注"未识别到有效库存数据"。

5. 输出格式铁则
必须只输出纯JSON字符串，不允许添加任何额外的文字、解释、注释、markdown格式、符号，不得增减字段、修改字段名、变更结构层级，严格遵循下方固定结构输出。

【固定输出JSON结构】
{size_stock_template}
"""


def build_context_parser_prompt(
    sizes: list[str],
    colors: list[str],
    mappings: dict[str, str],
) -> str:
    """根据实际产品数据构建智能体 B 的系统提示词。"""
    sizes_str = json.dumps(sizes, ensure_ascii=False) if sizes else '["暂无可选尺码"]'
    colors_str = json.dumps(colors, ensure_ascii=False) if colors else '["暂无可选颜色"]'
    mapping_str = json.dumps(mappings, ensure_ascii=False) if mappings else '{}'

    # 动态构建 size_stock 示例：所有可选尺码都出现在模板中
    if sizes:
        size_stock_entries = ", ".join(f'"{s}": "数量或0"' for s in sizes)
        size_stock_example = "{ " + size_stock_entries + " }"
    else:
        size_stock_example = '{ "尺码名": "数量或0" }'

    template_json = (
        "{\n"
        '  "style_code": "转换后的目标款号，无匹配填null",\n'
        '  "original_style_code": "图片中识别到的原始手写款号，未识别填null",\n'
        '  "inventory": [\n'
        "    {\n"
        '      "color": "匹配到的可选颜色标准名称",\n'
        f'      "size_stock": {size_stock_example}\n'
        "    }\n"
        "  ],\n"
        '  "remarks": "异常说明，无异常填无"\n'
        "}"
    )

    return _CONTEXT_PARSER_PROMPT_TEMPLATE.format(
        sizes_list=sizes_str,
        colors_list=colors_str,
        style_mapping=mapping_str,
        size_stock_template=template_json,
    )


def convert_inventory_result_to_standard(ai_result: dict[str, Any]) -> dict[str, Any]:
    """将智能体 B 新格式（style_code + inventory）转换为下游兼容的标准格式。

    新格式:
        {"style_code": "...", "original_style_code": "...", "inventory": [...], "remarks": "..."}
    标准格式:
        {"items": [{"product_no": "...", "color": "...", "sizes": [...]}], ...}
    """
    # 如果已经是旧格式（包含 items 字段），直接返回
    if "items" in ai_result:
        return ai_result

    style_code = ai_result.get("style_code") or ""
    original = ai_result.get("original_style_code") or ""
    product_no = style_code or original or ""

    items: list[dict[str, Any]] = []
    for inv in ai_result.get("inventory") or []:
        color = str(inv.get("color") or "").strip()
        size_stock = inv.get("size_stock") or {}
        sizes = []
        for size_name, qty_val in size_stock.items():
            try:
                qty = int(qty_val)
            except (ValueError, TypeError):
                qty = 0
            sizes.append({"size": str(size_name).strip(), "qty": qty})
        if sizes and color:
            items.append({
                "product_no": product_no,
                "product_name": "",
                "color": color,
                "brand": "",
                "unit": "件",
                "price": 0,
                "discount": 1,
                "sizes": sizes,
                "remark": "",
            })

    remarks = str(ai_result.get("remarks") or "").strip()
    return {
        "customer_name": "",
        "contact_person": "",
        "order_date": "",
        "remark": remarks if remarks and remarks != "无" else "",
        "items": items,
        "uncertainties": [],
    }


def rotate_images_in_messages(
    context_messages: list[dict[str, Any]],
    angle: int,
) -> list[dict[str, Any]]:
    """将消息列表中的所有图片按指定角度旋转。

    angle: 正数=顺时针，负数=逆时针（如 90=顺时针90°, -90=逆时针90°）
    为 0 时直接返回原列表。仅处理包含 base64 数据的图片消息。
    """
    if angle == 0:
        return context_messages

    import io
    from PIL import Image

    # PIL 的 rotate() 正数=逆时针，所以取反：
    # AI 输出 90（顺时针90°）→ PIL rotate(-90) = 顺时针90°
    # AI 输出 -90（逆时针90°）→ PIL rotate(90) = 逆时针90°
    pil_angle = -angle

    rotated: list[dict[str, Any]] = []
    for msg in context_messages:
        if msg.get("type") != "image" or not msg.get("base64"):
            rotated.append(msg)
            continue
        try:
            raw = base64.b64decode(msg["base64"])
            img = Image.open(io.BytesIO(raw))
            img_rotated = img.rotate(pil_angle, expand=True)
            buf = io.BytesIO()
            fmt = "PNG" if (msg.get("mime") or "").endswith("png") else "JPEG"
            img_rotated.save(buf, format=fmt)
            new_b64 = base64.b64encode(buf.getvalue()).decode("ascii")
            new_msg = dict(msg)
            new_msg["base64"] = new_b64
            # 清除 oss_url，旋转后的图片需要重新上传
            new_msg.pop("oss_url", None)
            rotated.append(new_msg)
            logger.info("图片旋转: 顺时针 %d° 完成", angle)
        except Exception as exc:
            logger.warning("图片旋转失败 (angle=%d): %s", angle, exc)
            rotated.append(msg)
    return rotated


ai_order_parser = AIOrderParser()
