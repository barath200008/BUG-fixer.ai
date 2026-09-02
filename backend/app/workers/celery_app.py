"""
Mirrors: backend/src/jobs/queue.ts (BullMQ -> Celery)

STUB: Celery app is wired and importable so `celery -A app.workers.celery_app worker`
runs without crashing, but the actual task implementations (analysis pipeline
runner, sandbox execution, AI diagnosis, patch application, cleanup) land with
the Sandbox/Engine phase. Right now `run_analysis_task` only marks the run as
QUEUED in the DB; nothing actually executes the pipeline yet.
"""
from celery import Celery

from app.core.config import settings

celery_app = Celery("bugfixai", broker=settings.REDIS_URL, backend=settings.REDIS_URL)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
)


@celery_app.task(name="analysis.run")
def run_analysis_task(analysis_id: str, project_id: str, owner_id: str) -> None:
    # STUB: real pipeline execution (phases 1-8) is ported with the Sandbox/Engine phase.
    import structlog

    logger = structlog.get_logger(__name__)
    logger.warning(
        "run_analysis_task_stub_only",
        analysis_id=analysis_id,
        project_id=project_id,
        note="Pipeline execution not yet implemented — job accepted but no-op.",
    )
