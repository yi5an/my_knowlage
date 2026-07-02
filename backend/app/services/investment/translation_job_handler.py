"""``TaskJob`` handler that translates investment items to Chinese.

Registered under ``job_type='investment_translation'`` (see
:func:`fetch_job_handler.register`, which registers both investment job types).
Runs the :class:`InvestmentTranslationService` over items lacking ``title_zh``
for the job's workspace/source. Unlike the fetch handler, this one DOES use the
``llm_client`` passed by the worker.
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm import Session

from app.infrastructure.models import TaskJob
from app.services.investment.translation import InvestmentTranslationService
from app.services.structured_output import StructuredOutputClient

logger = logging.getLogger(__name__)

INVESTMENT_TRANSLATION_JOB_TYPE = "investment_translation"


class InvestmentTranslationJobHandler:
    """Translate all untranslated items in the job's workspace."""

    def handle(
        self,
        job: TaskJob,
        session: Session,
        llm_client: StructuredOutputClient,
    ) -> dict[str, Any]:
        workspace_id = (job.input or {}).get("workspace_id") or job.workspace_id
        source_id = (job.input or {}).get("source_id")

        # Limit per job to keep each call bounded; the fetch scheduler will
        # enqueue more translation jobs if many items are pending.
        result = InvestmentTranslationService(
            session=session, llm_client=llm_client
        ).translate_untranslated(workspace_id=workspace_id, limit=20)

        logger.info(
            "investment translation job %s (source=%s): %s",
            job.id,
            source_id,
            result,
        )
        return {"source_id": source_id, "workspace_id": workspace_id, **result}


_HANDLER = InvestmentTranslationJobHandler()
