"""Mirrors: backend/src/modules/ai/providers/anthropic.provider.ts"""
import httpx

from app.core.config import settings
from app.modules.ai.providers.base import AIProvider, ChatRequest


class AnthropicProvider(AIProvider):
    async def chat(self, request: ChatRequest) -> str:
        try:
            if not request.api_key:
                raise ValueError("Anthropic API key is not configured")
            base_url = request.base_url or settings.ANTHROPIC_BASE_URL
            async with httpx.AsyncClient(timeout=120) as client:
                response = await client.post(
                    f"{base_url}/v1/messages",
                    headers={
                        "content-type": "application/json",
                        "x-api-key": request.api_key,
                        "anthropic-version": "2023-06-01",
                    },
                    json={
                        "model": request.model,
                        "system": request.system,
                        "messages": [{"role": "user", "content": request.user}],
                        "temperature": request.temperature,
                        "max_tokens": request.max_tokens,
                    },
                )
            if response.status_code >= 400:
                raise ValueError(f"Anthropic request failed with status {response.status_code}")
            data = response.json()
            text = "\n".join(part.get("text", "") for part in data.get("content", [])).strip()
            if not text:
                raise ValueError("Anthropic returned an empty response")
            return text
        except Exception as exc:  # noqa: BLE001
            raise ValueError(f"Anthropic provider error: {exc}") from exc
