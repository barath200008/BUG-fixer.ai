"""
Real multi-provider LLM client.

Supports five provider families used by the model catalog:
  - "openai"      -> OpenAI /v1/chat/completions
  - "groq"        -> Groq   /openai/v1/chat/completions (OpenAI-compatible, free tier)
  - "openrouter"  -> OpenRouter /api/v1/chat/completions (OpenAI-compatible, has free models)
  - "deepseek"    -> DeepSeek /v1/chat/completions (OpenAI-compatible)
  - "anthropic"   -> Anthropic /v1/messages (Claude)
  - "google"      -> Google Generative Language API (Gemini, has a free tier)

All five are reached through one function: `chat_complete`. Callers pass a
plain list of {"role": "system"|"user"|"assistant", "content": str} messages
and get back the assistant's text. No provider SDKs are required — everything
goes over `httpx` since each of these providers exposes a plain REST API.
"""
from __future__ import annotations

import json

import httpx

from app.core.config import settings


class ProviderError(Exception):
    """Raised when a provider call fails or isn't configured."""

    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(message)


_OPENAI_COMPATIBLE = {"openai", "groq", "openrouter", "deepseek"}

_KEY_FOR = {
    "openai": lambda: settings.OPENAI_API_KEY,
    "groq": lambda: settings.GROQ_API_KEY,
    "openrouter": lambda: settings.OPENROUTER_API_KEY,
    "deepseek": lambda: settings.DEEPSEEK_API_KEY,
    "anthropic": lambda: settings.ANTHROPIC_API_KEY,
    "google": lambda: settings.GOOGLE_API_KEY,
}

_BASE_URL_FOR = {
    "openai": lambda: settings.OPENAI_BASE_URL,
    "groq": lambda: settings.GROQ_BASE_URL,
    "openrouter": lambda: settings.OPENROUTER_BASE_URL,
    "deepseek": lambda: settings.DEEPSEEK_BASE_URL,
    "anthropic": lambda: settings.ANTHROPIC_BASE_URL,
    "google": lambda: settings.GOOGLE_BASE_URL,
}


def is_configured(provider: str) -> bool:
    getter = _KEY_FOR.get(provider)
    return bool(getter and getter())


async def chat_complete(
    provider: str,
    model: str,
    messages: list[dict],
    *,
    json_mode: bool = False,
    max_tokens: int = 2000,
    temperature: float = 0.3,
) -> str:
    """Sends `messages` to the given provider/model and returns the assistant's reply text."""
    if provider not in _KEY_FOR:
        raise ProviderError("UNKNOWN_PROVIDER", f"Unknown AI provider: {provider}")

    api_key = _KEY_FOR[provider]()
    if not api_key:
        raise ProviderError(
            "PROVIDER_NOT_CONFIGURED",
            f"The '{provider}' provider has no API key configured on the server yet.",
        )

    if provider in _OPENAI_COMPATIBLE:
        return await _openai_compatible_call(provider, model, messages, api_key, json_mode, max_tokens, temperature)
    if provider == "anthropic":
        return await _anthropic_call(model, messages, api_key, max_tokens, temperature)
    if provider == "google":
        return await _google_call(model, messages, api_key, json_mode, max_tokens, temperature)

    raise ProviderError("UNKNOWN_PROVIDER", f"Unknown AI provider: {provider}")


async def _openai_compatible_call(
    provider: str,
    model: str,
    messages: list[dict],
    api_key: str,
    json_mode: bool,
    max_tokens: int,
    temperature: float,
) -> str:
    base_url = _BASE_URL_FOR[provider]().rstrip("/")
    body: dict = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    if json_mode:
        body["response_format"] = {"type": "json_object"}

    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    if provider == "openrouter":
        headers["HTTP-Referer"] = "https://bugfixer.ai"
        headers["X-Title"] = "BugFixer.ai"

    async with httpx.AsyncClient(timeout=60.0) as client:
        try:
            resp = await client.post(f"{base_url}/chat/completions", json=body, headers=headers)
        except httpx.HTTPError as exc:
            raise ProviderError("PROVIDER_UNREACHABLE", f"Could not reach {provider}: {exc}") from exc

    if resp.status_code >= 400:
        raise ProviderError("PROVIDER_ERROR", f"{provider} returned {resp.status_code}: {resp.text[:300]}")

    data = resp.json()
    try:
        return data["choices"][0]["message"]["content"] or ""
    except (KeyError, IndexError) as exc:
        raise ProviderError("PROVIDER_BAD_RESPONSE", f"Unexpected response shape from {provider}") from exc


async def _anthropic_call(model: str, messages: list[dict], api_key: str, max_tokens: int, temperature: float) -> str:
    base_url = settings.ANTHROPIC_BASE_URL.rstrip("/")
    system_parts = [m["content"] for m in messages if m["role"] == "system"]
    convo = [m for m in messages if m["role"] != "system"]

    body = {
        "model": model,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "messages": convo,
    }
    if system_parts:
        body["system"] = "\n\n".join(system_parts)

    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(timeout=60.0) as client:
        try:
            resp = await client.post(f"{base_url}/v1/messages", json=body, headers=headers)
        except httpx.HTTPError as exc:
            raise ProviderError("PROVIDER_UNREACHABLE", f"Could not reach anthropic: {exc}") from exc

    if resp.status_code >= 400:
        raise ProviderError("PROVIDER_ERROR", f"anthropic returned {resp.status_code}: {resp.text[:300]}")

    data = resp.json()
    try:
        return "".join(block.get("text", "") for block in data.get("content", []))
    except (KeyError, TypeError) as exc:
        raise ProviderError("PROVIDER_BAD_RESPONSE", "Unexpected response shape from anthropic") from exc


async def _google_call(
    model: str, messages: list[dict], api_key: str, json_mode: bool, max_tokens: int, temperature: float
) -> str:
    base_url = settings.GOOGLE_BASE_URL.rstrip("/")
    system_parts = [m["content"] for m in messages if m["role"] == "system"]
    contents = [
        {"role": "model" if m["role"] == "assistant" else "user", "parts": [{"text": m["content"]}]}
        for m in messages
        if m["role"] != "system"
    ]

    generation_config: dict = {"maxOutputTokens": max_tokens, "temperature": temperature}
    if json_mode:
        generation_config["response_mime_type"] = "application/json"

    body: dict = {"contents": contents, "generationConfig": generation_config}
    if system_parts:
        body["systemInstruction"] = {"parts": [{"text": "\n\n".join(system_parts)}]}

    url = f"{base_url}/models/{model}:generateContent"

    async with httpx.AsyncClient(timeout=60.0) as client:
        try:
            resp = await client.post(url, json=body, params={"key": api_key})
        except httpx.HTTPError as exc:
            raise ProviderError("PROVIDER_UNREACHABLE", f"Could not reach google: {exc}") from exc

    if resp.status_code >= 400:
        raise ProviderError("PROVIDER_ERROR", f"google returned {resp.status_code}: {resp.text[:300]}")

    data = resp.json()
    try:
        candidate = data["candidates"][0]
        parts = candidate["content"]["parts"]
        return "".join(p.get("text", "") for p in parts)
    except (KeyError, IndexError) as exc:
        raise ProviderError("PROVIDER_BAD_RESPONSE", "Unexpected response shape from google") from exc


def extract_json(text: str) -> dict:
    """Best-effort JSON extraction: strips ```json fences and grabs the outermost {...}."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:]
        cleaned = cleaned.strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start != -1 and end != -1 and end > start:
        return json.loads(cleaned[start : end + 1])
    raise ProviderError("PROVIDER_BAD_RESPONSE", "Model did not return valid JSON")
