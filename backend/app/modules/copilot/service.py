"""Mirrors: backend/src/modules/copilot/copilot.service.ts

NOTE: conversation/message persistence below is real. Generating an actual
AI reply is not — the AI providers module is still a stub (see
app/modules/ai/service.py), so `send_message` responds with a clear,
honest placeholder message instead of silently pretending to think.
Swap `_generate_reply` for a real call once a provider is wired up.
"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.common.errors.app_error import AppError
from app.models.copilot import CodeChangeProposal, CopilotConversation, CopilotMessage
from app.models.enums import ProposalStatus

_MESSAGE_LOAD_OPTS = selectinload(CopilotConversation.messages).selectinload(CopilotMessage.proposal)


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


def _generate_reply(user_text: str) -> str:
    # Placeholder until a real provider (OpenAI/Anthropic/etc.) is wired up
    # for this module. Keeping this honest rather than faking a response.
    return (
        "I received your message, but AI chat isn't connected to a model provider yet "
        "in this build — that part of the backend is still being ported. Once it's wired "
        "up, I'll be able to actually respond to things like this."
    )


async def send_message(
    db: AsyncSession, user_id: str, conversation_id: str, text: str, provider: str | None, model: str | None
) -> CopilotMessage:
    convo = await _conversation_for(db, user_id, conversation_id)

    user_message = CopilotMessage(conversationId=convo.id, sender="user", text=text)
    db.add(user_message)
    await db.flush()

    reply_text = _generate_reply(text)
    ai_message = CopilotMessage(
        conversationId=convo.id,
        sender="ai",
        text=reply_text,
        modelUsed=model,
        provider=provider,
    )
    db.add(ai_message)
    await db.commit()
    await db.refresh(ai_message)
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