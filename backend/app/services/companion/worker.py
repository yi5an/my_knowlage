"""Durable task-job handler for proactive companion insights."""

from typing import Any

from sqlalchemy.orm import Session

from app.infrastructure.models import TaskJob
from app.services.companion.service import CompanionService
from app.services.structured_output import StructuredOutputClient

COMPANION_INSIGHTS_JOB_TYPE = "companion_insights"


class CompanionInsightJobHandler:
    def handle(
        self,
        job: TaskJob,
        session: Session,
        llm_client: StructuredOutputClient,
    ) -> dict[str, Any]:
        session_id = str((job.input or {}).get("companion_session_id") or job.target_id or "")
        if not session_id:
            raise ValueError("companion_insights job requires companion_session_id")
        insights = CompanionService(session, llm_client).run_insight_job(session_id, job.id)
        return {"companion_session_id": session_id, "insights_created": len(insights)}


def register() -> None:
    from app.services import task_worker

    task_worker._HANDLERS[COMPANION_INSIGHTS_JOB_TYPE] = CompanionInsightJobHandler()
