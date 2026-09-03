"""
Mirrors: backend/src/modules/ai/ai.service.ts

Real implementation: builds a diagnosis prompt from the bug + (best-effort)
surrounding source context, calls the user's configured provider/model
through app.modules.ai.providers, and parses the model's JSON reply into
the shape fixes.service.generate_fix expects.
"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.common.errors.app_error import AppError
from app.models.bug import Bug
from app.models.project import Project
from app.modules.ai.catalog import resolve_default
from app.modules.ai.providers import ProviderError, chat_complete, extract_json, is_configured
from app.modules.settings.service import get_or_create_user_setting

_SYSTEM_PROMPT = """You are BugFixer.ai's automated bug-diagnosis engine. Given a bug report \
(and, when available, the surrounding source code), respond with ONLY a JSON object — no prose, \
no markdown fences — with exactly these keys:

{
  "explanation": "1-3 sentences on the root cause",
  "patchSummary": "one short sentence describing the fix",
  "unifiedDiff": "a unified diff (git-style, with ---/+++ and @@ hunks) implementing the fix",
  "originalCode": "the exact original snippet being replaced, or null if not applicable",
  "proposedCode": "the exact replacement snippet, or null if not applicable",
  "confidence": <integer 0-100, your confidence the fix is correct>,
  "estimatedMinutes": <integer, rough human review time in minutes>
}

If you don't have enough context to produce a real diff, still return valid JSON with your best-effort
explanation and a conservative confidence score rather than refusing."""


async def _load_bug_with_context(db: AsyncSession, user_id: str, bug_id: str) -> tuple[Bug, str | None]:
    stmt = (
        select(Bug)
        .join(Project, Bug.projectId == Project.id)
        .where(Bug.id == bug_id, Project.ownerId == user_id)
        .options(selectinload(Bug.project).selectinload(Project.workspace))
    )
    bug = (await db.execute(stmt)).scalar_one_or_none()
    if bug is None:
        raise AppError(404, "BUG_NOT_FOUND", "Bug was not found")

    source_snippet: str | None = None
    workspace = getattr(bug.project, "workspace", None)
    if workspace and workspace.rootPath and bug.filePath:
        import os

        from app.common.utils.safe_path import resolve_safe_path

        try:
            target = resolve_safe_path(workspace.rootPath, bug.filePath)
            if os.path.isfile(target) and os.path.getsize(target) < 200_000:
                with open(target, "r", encoding="utf-8", errors="replace") as f:
                    lines = f.read().split("\n")
                if bug.lineNumber:
                    start = max(0, bug.lineNumber - 30)
                    end = min(len(lines), bug.lineNumber + 30)
                    snippet = "\n".join(lines[start:end])
                else:
                    snippet = "\n".join(lines[:120])
                source_snippet = snippet[:8000]
        except Exception:  # noqa: BLE001 — best-effort context only, never block diagnosis on this
            source_snippet = None

    return bug, source_snippet


def _build_user_prompt(bug: Bug, source_snippet: str | None) -> str:
    parts = [
        f"Bug: {bug.title}",
        f"Severity: {bug.severity.value if hasattr(bug.severity, 'value') else bug.severity}",
        f"Component: {bug.component}",
        f"Language: {bug.language}",
    ]
    if bug.filePath:
        parts.append(f"File: {bug.filePath}" + (f":{bug.lineNumber}" if bug.lineNumber else ""))
    if bug.description:
        parts.append(f"Description: {bug.description}")
    if bug.stackTrace:
        parts.append(f"Stack trace:\n{bug.stackTrace[:2000]}")
    if source_snippet:
        parts.append(f"Surrounding source ({bug.filePath}):\n```{bug.language}\n{source_snippet}\n```")
    else:
        parts.append("(No source file could be read for additional context — diagnose from the report alone.)")
    return "\n\n".join(parts)


async def diagnose_bug(
    db, user_id: str, project_id: str, bug_id: str, provider: str | None = None, model: str | None = None
) -> dict:
    bug, source_snippet = await _load_bug_with_context(db, user_id, bug_id)

    if not provider or not model:
        user_setting = await get_or_create_user_setting(db, user_id)
        provider = provider or user_setting.primaryProvider.value
        model = model or user_setting.primaryModel

    if not is_configured(provider):
        fallback_provider, fallback_model = resolve_default()
        if not is_configured(fallback_provider):
            raise AppError(
                424,
                "PROVIDER_NOT_CONFIGURED",
                "No AI provider is configured on the server yet. Add a free-tier key "
                "(Groq or Google Gemini both work) in the backend .env, then try again.",
            )
        provider, model = fallback_provider, fallback_model

    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": _build_user_prompt(bug, source_snippet)},
    ]

    try:
        raw = await chat_complete(provider, model, messages, json_mode=True, max_tokens=2000, temperature=0.2)
        parsed = extract_json(raw)
    except ProviderError as exc:
        raise AppError(502, exc.code, f"AI diagnosis failed: {exc.message}") from exc

    return {
        "provider": provider,
        "model": model,
        "confidence": int(parsed.get("confidence", 60)),
        "explanation": str(parsed.get("explanation", "The model did not provide an explanation.")),
        "patchSummary": str(parsed.get("patchSummary", "Proposed fix")),
        "unifiedDiff": str(parsed.get("unifiedDiff", "")),
        "originalCode": parsed.get("originalCode"),
        "proposedCode": parsed.get("proposedCode"),
        "affectedFiles": [bug.filePath] if bug.filePath else [],
        "estimatedMinutes": int(parsed.get("estimatedMinutes", 10)),
    }
