import base64
import json
from typing import Any

import httpx

from app.config import settings


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
        self.base_url = settings.OPENAI_BASE_URL.rstrip("/")

    def _ensure_enabled(self):
        if not settings.OPENAI_API_KEY:
            raise AIOrderParserError("未配置 OPENAI_API_KEY，无法进行 AI 解析")

    async def _chat(self, model: str, messages: list[dict[str, Any]]) -> dict[str, Any]:
        self._ensure_enabled()
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(
                f"{self.base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {settings.OPENAI_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
                    "temperature": 0.1,
                    "response_format": {"type": "json_object"},
                    "messages": messages,
                },
            )
        response.raise_for_status()
        payload = response.json()
        content = (((payload.get("choices") or [{}])[0].get("message") or {}).get("content") or "{}").strip()
        try:
            return json.loads(content)
        except Exception as exc:
            raise AIOrderParserError(f"AI 返回内容不是有效 JSON: {content[:200]}") from exc

    async def parse_text(self, text: str, customer_hint: str = "") -> dict[str, Any]:
        return await self._chat(
            settings.OPENAI_MODEL,
            [
                {"role": "system", "content": ORDER_PARSE_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": f"客户提示: {customer_hint or '无'}\n原始文本:\n{text}",
                },
            ],
        )

    async def parse_image_base64(self, image_base64: str, mime_type: str = "image/png", extra_text: str = "") -> dict[str, Any]:
        return await self._chat(
            settings.OPENAI_VISION_MODEL,
            [
                {"role": "system", "content": ORDER_PARSE_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": f"请解析图片中的下单信息。补充说明: {extra_text or '无'}"},
                        {"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{image_base64}"}},
                    ],
                },
            ],
        )

    async def parse_excel_summary(self, file_name: str, text_summary: str, customer_hint: str = "") -> dict[str, Any]:
        return await self._chat(
            settings.OPENAI_MODEL,
            [
                {"role": "system", "content": ORDER_PARSE_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": f"文件名: {file_name}\n客户提示: {customer_hint or '无'}\n表格摘要:\n{text_summary}",
                },
            ],
        )


ai_order_parser = AIOrderParser()
