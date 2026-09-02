"""
Mirrors: backend/src/common/websocket/{realtime.gateway,events}.ts

STUB: no-op publish until the full WebSocket gateway (Redis pub/sub +
per-project rooms) is ported as part of the Sandbox/Workers phase.
Kept as a stable import target so pipeline code doesn't need rewiring later.
"""
import structlog

logger = structlog.get_logger(__name__)


REALTIME_EVENTS = {
    "phase_started": "analysis.phase.started",
    "phase_progress": "analysis.phase.progress",
    "log_created": "analysis.log.created",
}


class RealtimeGateway:
    async def publish(self, project_id: str, message: dict) -> None:
        # STUB: real implementation will push to Redis pub/sub -> WebSocket clients.
        logger.debug("realtime_publish_stub", project_id=project_id, message_type=message.get("type"))
