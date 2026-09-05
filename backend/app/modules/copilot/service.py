"""Mirrors: backend/src/modules/copilot/copilot.service.ts

Conversation/message persistence, plus real AI replies via
app.modules.ai.service.copilot_reply. When the model returns a proposal,
it's persisted as a CodeChangeProposal linked to the AI's message.
"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.common.errors.app_error import AppError
from app.models.copilot import CodeChangeProposal, CopilotConversation, CopilotMessage
from app.models.enums import ProposalStatus
from app.modules.ai.service import copilot_reply

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


async def send_message(
    db: AsyncSession, user_id: str, conversation_id: str, text: str, provider: str | None, model: str | None
) -> CopilotMessage:
    convo = await _conversation_for(db, user_id, conversation_id)

    user_message = CopilotMessage(conversationId=convo.id, sender="user", text=text)
    db.add(user_message)
    await db.flush()

    try:
        reply = await copilot_reply(db, user_id, convo.projectId, text, provider, model)
        reply_result = reply["result"] or {}
        reply_text = str(reply_result.get("answer", "")) or "The model returned an empty answer."
        used_provider, used_model = reply["provider"], reply["model"]
    except Exception as exc:  # noqa: BLE001
        # Keep the conversation usable even if the provider call fails
        # (missing key, network error, bad JSON, etc.) rather than 500ing
        # the whole endpoint and losing the user's message.
        reply_text = f"I couldn't get a response from the AI provider: {exc}"
        reply_result = {}
        used_provider, used_model = provider, model

    ai_message = CopilotMessage(
        conversationId=convo.id,
        sender="ai",
        text=reply_text,
        modelUsed=used_model,
        provider=used_provider,
    )
    db.add(ai_message)
    await db.flush()

    proposal_data = reply_result.get("proposal") if isinstance(reply_result, dict) else None
    if isinstance(proposal_data, dict):
        db.add(
            CodeChangeProposal(
                conversationId=convo.id,
                messageId=ai_message.id,
                file=str(proposal_data.get("file", "")),
                title=str(proposal_data.get("title", "")),
                description=str(proposal_data.get("description", "")),
                explanation=str(proposal_data.get("explanation", "")),
                startLine=int(proposal_data.get("startLine", 0) or 0),
                endLine=int(proposal_data.get("endLine", 0) or 0),
                originalCode=str(proposal_data.get("originalCode", "")),
                proposedCode=str(proposal_data.get("proposedCode", "")),
                diffSummary=str(proposal_data.get("diffSummary", "")),
            )
        )

    await db.commit()
    stmt = (
        select(CopilotMessage)
        .where(CopilotMessage.id == ai_message.id)
        .options(selectinload(CopilotMessage.proposal))
    )
    return (await db.execute(stmt)).scalar_one()


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