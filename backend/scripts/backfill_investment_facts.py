"""Enqueue fact extraction jobs for existing investment items.

Usage:
    python -m scripts.backfill_investment_facts --workspace-id ws_default --limit 500
"""

from __future__ import annotations

import argparse
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.infrastructure.database import SessionLocal
from app.infrastructure.models import InvestmentItem, TaskJob
from app.services.investment.fact_extraction import INVESTMENT_FACT_EXTRACTION_JOB_TYPE


def enqueue_fact_backfill_jobs(
    session: Session,
    *,
    workspace_id: str = "ws_default",
    source_id: str | None = None,
    limit: int = 500,
) -> dict[str, int]:
    conditions = [InvestmentItem.workspace_id == workspace_id]
    if source_id:
        conditions.append(InvestmentItem.source_id == source_id)
    items = list(
        session.scalars(
            select(InvestmentItem)
            .where(*conditions)
            .order_by(InvestmentItem.published_at.desc().nullslast(), InvestmentItem.created_at)
            .limit(limit)
        )
    )
    created = 0
    skipped = 0
    for item in items:
        existing = session.scalar(
            select(TaskJob).where(
                TaskJob.workspace_id == workspace_id,
                TaskJob.job_type == INVESTMENT_FACT_EXTRACTION_JOB_TYPE,
                TaskJob.target_type == "investment_item",
                TaskJob.target_id == item.id,
                TaskJob.status.in_(("pending", "running")),
            )
        )
        if existing is not None:
            skipped += 1
            continue
        session.add(
            TaskJob(
                id=f"job_{uuid4().hex}",
                workspace_id=workspace_id,
                job_type=INVESTMENT_FACT_EXTRACTION_JOB_TYPE,
                target_type="investment_item",
                target_id=item.id,
                status="pending",
                input={"workspace_id": workspace_id, "item_id": item.id},
            )
        )
        created += 1
    session.commit()
    return {"items_seen": len(items), "jobs_created": created, "jobs_skipped": skipped}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace-id", default="ws_default")
    parser.add_argument("--source-id")
    parser.add_argument("--limit", type=int, default=500)
    args = parser.parse_args()
    with SessionLocal() as session:
        result = enqueue_fact_backfill_jobs(
            session,
            workspace_id=args.workspace_id,
            source_id=args.source_id,
            limit=args.limit,
        )
    print(result)


if __name__ == "__main__":
    main()
