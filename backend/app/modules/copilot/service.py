"""Mirrors: backend/src/modules/copilot/copilot.service.ts

Chat replies are real: `send_message` calls the user's configured
provider/model (app.modules.ai.providers) with the recent conversation
history as context. If no provider is configured on the server yet, the
error surfaces clearly to the UI instead of a fake response.
"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.common.errors.app_error import AppError
from app.models.copilot import CodeChangeProposal, CopilotConversation, CopilotMessage
from app.models.enums import ProposalStatus
from app.modules.ai.catalog import resolve_default
from app.modules.ai.providers import ProviderError, chat_complete, is_configured
from app.modules.settings.service import get_or_create_user_setting

_MESSAGE_LOAD_OPTS = selectinload(CopilotConversation.messages).selectinload(CopilotMessage.proposal)

_SYSTEM_PROMPT = (
    "You are the BugFixer.ai workspace copilot. You help the developer understand their "
    "codebase, debug issues, and reason about fixes. Be concise and concrete. If you "
    "reference code, use fenced code blocks. You do not have direct file access in this "
    "chat — if you need to see a file, ask the developer to paste it or open it in the editor."
)
_HISTORY_LIMIT = 20


async def create_conversation(db: AsyncSession, user_id: str, project_id: str | None) -> CopilotConversation:
    convo = CopilotConversation(userId=user_id, projectId=project_id)
    db.add(convo)
    await db.commit()
    return await get_conversation(db, user_id, convo.id)


async def get_conversation(db: AsyncSession, user_id: str, conversation_id: str) -> CopilotConversation:
    stmt = (
        select(CopilotConversation)
        .where(CopilotConversation.id == conversation_id, CopilotConversation.userId == user_id)
        .options(_MESSAGE_LOAD_OPTS)
    )
    convo = (await db.execute(stmt)).scalar_one_or_none()
    if convo is None:
        raise AppError(404, "CONVERSATION_NOT_FOUND", "Conversation was not found")
    return convo


async def _conversation_for(db: AsyncSession, user_id: str, conversation_id: str) -> CopilotConversation:
    stmt = select(CopilotConversation).where(
        CopilotConversation.id == conversation_id, CopilotConversation.userId == user_id
    )
    convo = (await db.execute(stmt)).scalar_one_or_none()
    if convo is None:
        raise AppError(404, "CONVERSATION_NOT_FOUND", "Conversation was not found")
    return convo


async def _resolve_provider_model(db: AsyncSession, user_id: str, provider: str | None, model: str | None) -> tuple[str, str]:
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
        return fallback_provider, fallback_model
    return provider, model


async def send_message(
    db: AsyncSession, user_id: str, conversation_id: str, text: str, provider: str | None, model: str | None
) -> CopilotMessage:
    convo = await _conversation_for(db, user_id, conversation_id)

    user_message = CopilotMessage(conversationId=convo.id, sender="user", text=text)
    db.add(user_message)
    await db.flush()

    resolved_provider, resolved_model = await _resolve_provider_model(db, user_id, provider, model)

    # Recent history gives the model conversational context.
    history_stmt = (
        select(CopilotMessage)
        .where(CopilotMessage.conversationId == convo.id)
        .order_by(CopilotMessage.createdAt.desc())
        .limit(_HISTORY_LIMIT)
    )
    recent = list(reversed((await db.execute(history_stmt)).scalars().all()))
    messages = [{"role": "system", "content": _SYSTEM_PROMPT}]
    for m in recent:
        messages.append({"role": "user" if m.sender == "user" else "assistant", "content": m.text})

    try:
        reply_text = await chat_complete(resolved_provider, resolved_model, messages, max_tokens=1500)
    except ProviderError as exc:
        raise AppError(502, exc.code, f"The agent couldn't reach {resolved_provider}: {exc.message}") from exc

    ai_message = CopilotMessage(
        conversationId=convo.id,
        sender="ai",
        text=reply_text,
        modelUsed=resolved_model,
        provider=resolved_provider,
    )
    db.add(ai_message)
    await db.commit()
    await db.refresh(ai_message)
    # A brand-new message never has a proposal yet. Setting this explicitly (rather than
    # letting the response schema touch the unloaded relationship) avoids an async lazy-load
    # crash — SQLAlchemy's default lazy loading isn't awaitable and blows up under FastAPI's
    # async session with a generic 500 if something tries to read it during serialization.
    ai_message.proposal = None
    return ai_message


async def set_proposal_status(db: AsyncSession, user_id: str, proposal_id: str, status: str) -> CodeChangeProposal:
    try:
        status_enum = ProposalStatus(status)
    except ValueError:
        raise AppError(400, "INVALID_STATUS", f"Unknown proposal status: {status}")

    stmt = (
        select(CodeChangeProposal)
        .join(CopilotConversation, CodeChangeProposal.conversationId == CopilotConversation.id)
        .where(CodeChangeProposal.id == proposal_id, CopilotConversation.userId == user_id)
    )
    proposal = (await db.execute(stmt)).scalar_one_or_none()
    if proposal is None:
        raise AppError(404, "PROPOSAL_NOT_FOUND", "Proposal was not found")

    proposal.status = status_enum
    await db.commit()
    await db.refresh(proposal)
    return proposal