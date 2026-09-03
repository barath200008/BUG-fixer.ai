"""
Model catalog: every model the app can offer in the model selector, tagged
with whether the provider is genuinely free-tier and whether a server-side
key is currently configured for it.

"free" here means: this provider offers this model at no cost to *you* (the
app operator) up to a generous quota, so once you drop a key in `.env`,
every signed-in user gets it for free. OpenAI and Anthropic don't currently
offer an ongoing free API tier, so those stay marked free=False — they'll
still work if you add a paid key, they just won't be pre-selected as the
default for new users.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.core.config import settings
from app.modules.ai.providers import is_configured


@dataclass(frozen=True)
class ModelInfo:
    id: str  # stable id used by the frontend, e.g. "groq:openai/gpt-oss-120b"
    provider: str
    model: str
    name: str
    free: bool
    contextWindow: str
    description: str


CATALOG: list[ModelInfo] = [
    # --- Groq: fast inference, generous free tier, hosts OpenAI's open GPT-OSS models ---
    ModelInfo(
        id="groq:openai/gpt-oss-120b",
        provider="groq",
        model="openai/gpt-oss-120b",
        name="GPT-OSS 120B (Groq)",
        free=True,
        contextWindow="128k tokens",
        description="OpenAI's open-weight 120B model running on Groq's free-tier inference.",
    ),
    ModelInfo(
        id="groq:openai/gpt-oss-20b",
        provider="groq",
        model="openai/gpt-oss-20b",
        name="GPT-OSS 20B (Groq)",
        free=True,
        contextWindow="128k tokens",
        description="Smaller, faster open-weight GPT-OSS model, still on Groq's free tier.",
    ),
    ModelInfo(
        id="groq:llama-3.3-70b-versatile",
        provider="groq",
        model="llama-3.3-70b-versatile",
        name="Llama 3.3 70B (Groq)",
        free=True,
        contextWindow="128k tokens",
        description="Meta's Llama 3.3 70B, free-tier inference via Groq.",
    ),
    # --- Google Gemini: has an actual free API tier ---
    ModelInfo(
        id="google:gemini-2.0-flash",
        provider="google",
        model="gemini-2.0-flash",
        name="Gemini 2.0 Flash",
        free=True,
        contextWindow="1M tokens",
        description="Google's fast, free-tier Gemini model with a huge context window.",
    ),
    ModelInfo(
        id="google:gemini-1.5-flash",
        provider="google",
        model="gemini-1.5-flash",
        name="Gemini 1.5 Flash",
        free=True,
        contextWindow="1M tokens",
        description="Free-tier Gemini, good default for large-file/monorepo context.",
    ),
    # --- OpenRouter: some models are free-of-charge (":free" variants) ---
    ModelInfo(
        id="openrouter:deepseek/deepseek-chat-v3.1:free",
        provider="openrouter",
        model="deepseek/deepseek-chat-v3.1:free",
        name="DeepSeek V3.1 (free, OpenRouter)",
        free=True,
        contextWindow="64k tokens",
        description="DeepSeek's chat model on OpenRouter's free tier — strong at reasoning.",
    ),
    # --- Anthropic Claude: no ongoing free API tier; needs a paid key ---
    ModelInfo(
        id="anthropic:claude-sonnet-4-6",
        provider="anthropic",
        model="claude-sonnet-4-6",
        name="Claude Sonnet",
        free=False,
        contextWindow="200k tokens",
        description="Anthropic's Claude. Needs a paid ANTHROPIC_API_KEY — no free API tier exists.",
    ),
    # --- OpenAI: no ongoing free API tier; needs a paid key ---
    ModelInfo(
        id="openai:gpt-4o-mini",
        provider="openai",
        model="gpt-4o-mini",
        name="GPT-4o mini",
        free=False,
        contextWindow="128k tokens",
        description="OpenAI's small flagship model. Needs a paid OPENAI_API_KEY.",
    ),
]


def list_models() -> list[dict]:
    return [
        {
            "id": m.id,
            "provider": m.provider,
            "model": m.model,
            "name": m.name,
            "free": m.free,
            "configured": is_configured(m.provider),
            "contextWindow": m.contextWindow,
            "description": m.description,
        }
        for m in CATALOG
    ]


def resolve_default() -> tuple[str, str]:
    """Picks the best available model: prefers free + configured, then the app's configured default."""
    for m in CATALOG:
        if m.free and is_configured(m.provider):
            return m.provider, m.model
    if is_configured(settings.DEFAULT_AI_PROVIDER):
        return settings.DEFAULT_AI_PROVIDER, settings.DEFAULT_AI_MODEL
    # Nothing configured at all — return the first free entry so the UI can
    # at least show *something* as selected, even though calls will 424 until
    # a key is added.
    first = CATALOG[0]
    return first.provider, first.model
