"""Mirrors: backend/src/modules/analysis/pipeline/pipeline.service.ts"""
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.websocket.realtime_gateway import REALTIME_EVENTS, RealtimeGateway
from app.models.analysis import PipelineLog, PipelinePhase
from app.models.enums import PhaseStatus


async def set_phase(
    db: AsyncSession,
    gateway: RealtimeGateway,
    analysis_id: str,
    number: int,
    status: str,
    project_id: str,
) -> PipelinePhase:
    stmt = select(PipelinePhase).where(
        PipelinePhase.analysisRunId == analysis_id, PipelinePhase.number == number
    )
    phase = (await db.execute(stmt)).scalar_one_or_none()
    if phase is None:
        raise ValueError("Pipeline phase not found")

    now = datetime.now(timezone.utc)
    phase.status = PhaseStatus(status)
    if status == "RUNNING":
        phase.startedAt = phase.startedAt or now
    else:
        phase.completedAt = now
        if phase.startedAt:
            phase.durationMs = int((now - phase.startedAt).total_seconds() * 1000)

    await db.commit()
    await db.refresh(phase)

    event_type = REALTIME_EVENTS["phase_started"] if status == "RUNNING" else REALTIME_EVENTS["phase_progress"]
    await gateway.publish(
        project_id,
        {
            "type": event_type,
            "projectId": project_id,
            "analysisId": analysis_id,
            "payload": {"id": phase.id, "number": phase.number, "status": phase.status},
        },
    )
    return phase


async def add_log(
    db: AsyncSession,
    gateway: RealtimeGateway,
    analysis_id: str,
    project_id: str,
    level: str,
    category: str,
    message: str,
    phase_id: str | None = None,
) -> PipelineLog:
    log = PipelineLog(
        analysisRunId=analysis_id,
        phaseId=phase_id,
        level=level,
        category=category,
        message=message,
    )
    db.add(log)
    await db.commit()
    await db.refresh(log)

    await gateway.publish(
        project_id,
        {
            "type": REALTIME_EVENTS["log_created"],
            "projectId": project_id,
            "analysisId": analysis_id,
            "payload": {"id": log.id, "level": log.level, "category": log.category, "message": log.message},
        },
    )
    return log
