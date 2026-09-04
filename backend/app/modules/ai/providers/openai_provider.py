"""Mirrors: backend/src/modules/ai/providers/openai.provider.ts"""
import httpx

from app.core.config import settings
from app.modules.ai.providers.base import AIProvider, ChatRequest


class OpenAIProvider(AIProvider):
    async def chat(self, request: ChatRequest) -> str:
        try:
            if not request.api_key:
                raise ValueError("OpenAI API key is not configured")
            base_url = request.base_url or settings.OPENAI_BASE_URL
            async with httpx.AsyncClient(timeout=120) as client:
                response = await client.post(
                    f"{base_url}/chat/completions",
                    headers={"content-type": "application/json", "authorization": f"Bearer {request.api_key}"},
                    json={
                        "model": request.model,
                        "messages": [
                            {"role": "system", "content": request.system},
                            {"role": "user", "content": request.user},
                        ],
                        "temperature": request.temperature,
                        "max_tokens": request.max_tokens,
                    },
                )
            if response.status_code >= 400:
                raise ValueError(f"OpenAI request failed with status {response.status_code}")
            data = response.json()
            text = (data.get("choices") or [{}])[0].get("message", {}).get("content")
            if not text:
                raise ValueError("OpenAI returned an empty response")
            return text
        except Exception as exc:  # noqa: BLE001
            raise ValueError(f"OpenAI provider error: {exc}") from exc
