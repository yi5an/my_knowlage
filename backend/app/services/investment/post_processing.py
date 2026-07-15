"""Shared post-processing queue helpers for investment items.

Ingestion paths are intentionally varied (manual items, RSS/official fetchers,
X web imports, YouTube summaries), but downstream work should be consistent and
scope-aware. This module owns that queueing contract.
"""

from __future__ import annotations

from uuid import uuid4

from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from app.infrastructure.models import InvestmentFact, InvestmentItem, TaskJob

INVESTMENT_TRANSLATION_JOB_TYPE = "investment_translation"
INVESTMENT_CLASSIFICATION_JOB_TYPE = "investment_classification"
INVESTMENT_FACT_EXTRACTION_JOB_TYPE = "investment_fact_extract"


def enqueue_investment_post_processing(
    session: Session,
    *,
    workspace_id: str,
    target_type: str,
    target_id: str,
    source_id: str | None = None,
    include_classification: bool = False,
    include_fact_extraction: bool = True,
) -> dict[str, bool]:
    """Queue bounded post-processing jobs for a source or a single item.

    Translation jobs are scoped by ``source_id`` or ``item_id`` so one source's
    retry cannot unexpectedly process another source's backlog. Classification
    is currently source-scoped because the classifier operates over fetched
    source batches.
    """
    item_id = target_id if target_type == "investment_item" else None
    translation_enqueued = False
    classification_enqueued = False
    fact_extraction_enqueued = False

    if _has_untranslated_items(
        session,
        workspace_id=workspace_id,
        source_id=source_id,
        item_id=item_id,
    ):
        translation_enqueued = _enqueue_unique_job(
            session,
            job_type=INVESTMENT_TRANSLATION_JOB_TYPE,
            workspace_id=workspace_id,
            target_type=target_type,
            target_id=target_id,
            source_id=source_id,
            item_id=item_id,
        )

    if include_classification and source_id is not None and _has_unclassified_items(
        session,
        workspace_id=workspace_id,
        source_id=source_id,
    ):
        classification_enqueued = _enqueue_unique_job(
            session,
            job_type=INVESTMENT_CLASSIFICATION_JOB_TYPE,
            workspace_id=workspace_id,
            target_type="investment_source",
            target_id=source_id,
            source_id=source_id,
            item_id=None,
        )

    if include_fact_extraction and _has_unextracted_fact_items(
        session,
        workspace_id=workspace_id,
        source_id=source_id,
        item_id=item_id,
    ):
        fact_extraction_enqueued = _enqueue_unique_job(
            session,
            job_type=INVESTMENT_FACT_EXTRACTION_JOB_TYPE,
            workspace_id=workspace_id,
            target_type=target_type,
            target_id=target_id,
            source_id=source_id,
            item_id=item_id,
        )

    return {
        "translation_enqueued": translation_enqueued,
        "classification_enqueued": classification_enqueued,
        "fact_extraction_enqueued": fact_extraction_enqueued,
    }


def _enqueue_unique_job(
    session: Session,
    *,
    job_type: str,
    workspace_id: str,
    target_type: str,
    target_id: str,
    source_id: str | None,
    item_id: str | None,
) -> bool:
    if _has_active_job(
        session,
        job_type=job_type,
        workspace_id=workspace_id,
        source_id=source_id,
        item_id=item_id,
    ):
        return False

    payload: dict[str, str] = {"workspace_id": workspace_id}
    if source_id is not None:
        payload["source_id"] = source_id
    if item_id is not None:
        payload["item_id"] = item_id

    session.add(
        TaskJob(
            id=f"job_{uuid4().hex}",
            workspace_id=workspace_id,
            job_type=job_type,
            target_type=target_type,
            target_id=target_id,
            status="pending",
            input=payload,
        )
    )
    return True


def _has_active_job(
    session: Session,
    *,
    job_type: str,
    workspace_id: str,
    source_id: str | None,
    item_id: str | None,
) -> bool:
    jobs = session.scalars(
        select(TaskJob).where(
            TaskJob.job_type == job_type,
            TaskJob.workspace_id == workspace_id,
            TaskJob.status.in_(("pending", "running")),
        )
    )
    for job in jobs:
        data = job.input or {}
        if item_id is not None:
            if data.get("item_id") == item_id:
                return True
            continue
        if source_id is not None:
            if data.get("source_id") == source_id:
                return True
            continue
        if "source_id" not in data and "item_id" not in data:
            return True
    return False


def _has_untranslated_items(
    session: Session,
    *,
    workspace_id: str,
    source_id: str | None = None,
    item_id: str | None = None,
) -> bool:
    conditions = [
        InvestmentItem.workspace_id == workspace_id,
        (InvestmentItem.title_zh.is_(None))
        | (InvestmentItem.summary.is_not(None) & InvestmentItem.summary_zh.is_(None)),
    ]
    if source_id is not None:
        conditions.append(InvestmentItem.source_id == source_id)
    if item_id is not None:
        conditions.append(InvestmentItem.id == item_id)
    return session.scalar(select(InvestmentItem.id).where(*conditions).limit(1)) is not None


def _has_unclassified_items(
    session: Session,
    *,
    workspace_id: str,
    source_id: str,
) -> bool:
    return (
        session.scalar(
            select(InvestmentItem.id)
            .where(
                InvestmentItem.workspace_id == workspace_id,
                InvestmentItem.source_id == source_id,
                InvestmentItem.suggested_importance.is_(None),
            )
            .limit(1)
        )
        is not None
    )


def _has_unextracted_fact_items(
    session: Session,
    *,
    workspace_id: str,
    source_id: str | None = None,
    item_id: str | None = None,
) -> bool:
    conditions = [
        InvestmentItem.workspace_id == workspace_id,
        ~exists().where(InvestmentFact.source_item_id == InvestmentItem.id),
    ]
    if source_id is not None:
        conditions.append(InvestmentItem.source_id == source_id)
    if item_id is not None:
        conditions.append(InvestmentItem.id == item_id)
    return session.scalar(select(InvestmentItem.id).where(*conditions).limit(1)) is not None
