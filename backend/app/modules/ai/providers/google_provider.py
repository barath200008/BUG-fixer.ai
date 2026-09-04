"""Mirrors: backend/src/modules/ai/providers/google.provider.ts"""
from urllib.parse import quote

import httpx

from app.core.config import settings
from app.modules.ai.providers.base import AIProvider, ChatRequest


class GoogleProvider(AIProvider):
    async def chat(self, request: ChatRequest) -> str:
        try:
            if not request.api_key:
                raise ValueError("Google API key is not configured")
            base_url = request.base_url or settings.GOOGLE_BASE_URL
            url = f"{base_url}/models/{quote(request.model)}:generateContent?key={quote(request.api_key)}"
            async with httpx.AsyncClient(timeout=120) as client:
                response = await client.post(
                    url,
                    headers={"content-type": "application/json"},
                    json={
                        "systemInstruction": {"parts": [{"text": request.system}]},
                        "contents": [{"role": "user", "parts": [{"text": request.user}]}],
                        "generationConfig": {
                            "temperature": request.temperature,
                            "maxOutputTokens": request.max_tokens,
                        },
                    },
                )
            if response.status_code >= 400:
                raise ValueError(f"Google request failed with status {response.status_code}")
            data = response.json()
            candidates = data.get("candidates") or []
            parts = (candidates[0].get("content", {}).get("parts") if candidates else []) or []
            text = "".join(p.get("text", "") for p in parts)
            if not text:
                raise ValueError("Google returned an empty response")
            return text
        except Exception as exc:  # noqa: BLE001
            raise ValueError(f"Google provider error: {exc}") from exc
