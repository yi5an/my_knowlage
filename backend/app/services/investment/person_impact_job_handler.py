"""Durable task handler for person-source market impact refreshes."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.infrastructure.models import TaskJob
from app.services.investment.person_impact import (
    PERSON_IMPACT_REFRESH_JOB_TYPE,
    PersonImpactProviderError,
    PersonImpactService,
)


class PersonImpactRefreshJobHandler:
    def handle(self, job: TaskJob, session: Session, llm_client: Any = None) -> dict[str, Any]:
        person_source_id = str((job.input or {}).get("person_source_id") or job.target_id or "")
        if not person_source_id:
            raise ValueError("person_impact_refresh job requires person_source_id")
        as_of = (job.input or {}).get("as_of")
        if as_of is not None and not isinstance(as_of, (str, datetime)):
            raise ValueError("person_impact_refresh job as_of must be ISO datetime")
        result = PersonImpactService.from_settings(session).rebuild_person(
            person_source_id=person_source_id,
            workspace_id=job.workspace_id,
            as_of=as_of,
        )
        provider_errors = int(result.get("provider_errors", 0))
        if provider_errors:
            raise PersonImpactProviderError(
                f"market provider failed for {provider_errors} person impact event(s)"
            )
        return {
            "person_source_id": person_source_id,
            "created": int(result.get("created", 0)),
            "computed": int(result.get("computed", 0)),
            "excluded": int(result.get("excluded", 0)),
            "insufficient": int(result.get("insufficient", 0)),
            "sample_count": int(result["profile"].sample_count),
            "valid_sample_count": int(result["profile"].valid_sample_count),
            "excluded_sample_count": int(result["profile"].excluded_sample_count),
        }


_HANDLER = PersonImpactRefreshJobHandler()


def register() -> None:
    from app.services import task_worker

    task_worker._HANDLERS[PERSON_IMPACT_REFRESH_JOB_TYPE] = _HANDLER


__all__ = [
    "PERSON_IMPACT_REFRESH_JOB_TYPE",
    "PersonImpactRefreshJobHandler",
    "register",
]
