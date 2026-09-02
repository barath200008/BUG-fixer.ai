"""
Mirrors: backend/src/modules/ai/ai.service.ts

STUB: diagnose_bug is a placeholder until the full AI providers module
(5 providers: OpenAI, Anthropic, Google, Groq, OpenRouter/DeepSeek via
openai-compatible, model-router, context-builder, prompt-builder) is
ported. Wired here so the fixes module has a stable import target.
"""
from app.common.errors.app_error import AppError


async def diagnose_bug(
    db, user_id: str, project_id: str, bug_id: str, provider: str | None = None, model: str | None = None
) -> dict:
    raise AppError(
        501,
        "NOT_IMPLEMENTED",
        "AI diagnosis is not yet wired up — the AI providers module hasn't been ported.",
    )
