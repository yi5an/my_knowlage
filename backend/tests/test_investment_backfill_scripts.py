"""Tests for investment backfill scripts."""

from __future__ import annotations

from collections.abc import Generator
from datetime import UTC, datetime

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.infrastructure.database import Base
from app.infrastructure.models import (
    InvestmentFact,
    InvestmentItem,
    InvestmentSignal,
    TaskJob,
    Workspace,
)
from app.schemas.investment import InvestmentTranslationItem, InvestmentTranslationSchema
from app.services.structured_output import MockStructuredOutputClient


def _session() -> Generator[Session, None, None]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    with session_factory() as session:
        session.add(Workspace(id="ws_default", name="Default"))
        session.commit()
        yield session


def test_backfill_investment_facts_enqueues_idempotent_jobs() -> None:
    from scripts.backfill_investment_facts import enqueue_fact_backfill_jobs

    session = next(_session())
    session.add_all(
        [
            InvestmentItem(
                id="inv_1",
                workspace_id="ws_default",
                dedupe_key="one",
                title="one",
            ),
            InvestmentItem(
                id="inv_2",
                workspace_id="ws_default",
                dedupe_key="two",
                title="two",
            ),
        ]
    )
    session.commit()

    first = enqueue_fact_backfill_jobs(session, workspace_id="ws_default")
    second = enqueue_fact_backfill_jobs(session, workspace_id="ws_default")

    jobs = list(session.scalars(select(TaskJob).order_by(TaskJob.target_id)))
    assert first == {"items_seen": 2, "jobs_created": 2, "jobs_skipped": 0}
    assert second == {"items_seen": 2, "jobs_created": 0, "jobs_skipped": 2}
    assert [job.target_id for job in jobs] == ["inv_1", "inv_2"]
    assert {job.job_type for job in jobs} == {"investment_fact_extract"}


def test_backfill_investment_signals_refreshes_existing_facts() -> None:
    from scripts.backfill_investment_signals import refresh_signal_backfill

    session = next(_session())
    session.add(
        InvestmentItem(
            id="inv_signal",
            workspace_id="ws_default",
            dedupe_key="signal",
            title="signal",
        )
    )
    session.add(
        InvestmentFact(
            id="fact_signal",
            workspace_id="ws_default",
            source_item_id="inv_signal",
            fact_text="NVIDIA data center demand remains strong.",
            fact_type="capex_signal",
            entities=["NVIDIA"],
            evidence_excerpt="NVIDIA data center demand remains strong.",
            confidence=0.8,
            verification_status="pending",
        )
    )
    session.commit()

    result = refresh_signal_backfill(session, workspace_id="ws_default")

    signal = session.scalar(select(InvestmentSignal))
    assert result == {"signals_created": 1}
    assert signal is not None
    assert signal.fact_ids == ["fact_signal"]


def test_backfill_investment_translations_runs_multiple_batches() -> None:
    from scripts.backfill_investment_translations import run_backfill

    session = next(_session())
    newer = InvestmentItem(
        id="inv_translate_newer",
        workspace_id="ws_default",
        dedupe_key="translate_newer",
        title="Newer English title",
        summary="newer summary",
        published_at=datetime(2026, 7, 14, tzinfo=UTC),
    )
    older = InvestmentItem(
        id="inv_translate_older",
        workspace_id="ws_default",
        dedupe_key="translate_older",
        title="Older English title",
        summary="older summary",
        published_at=datetime(2026, 7, 1, tzinfo=UTC),
    )
    session.add_all([older, newer])
    session.commit()
    client = MockStructuredOutputClient(
        outputs={
            InvestmentTranslationSchema: InvestmentTranslationSchema(
                translations=[
                    InvestmentTranslationItem(
                        item_id=newer.id,
                        title_zh="较新的英文标题",
                        summary_zh="较新的摘要",
                    ),
                    InvestmentTranslationItem(
                        item_id=older.id,
                        title_zh="较旧的英文标题",
                        summary_zh="较旧的摘要",
                    ),
                ]
            )
        }
    )

    result = run_backfill(
        session,
        client,
        workspace_id="ws_default",
        limit=1,
        batches=3,
    )

    session.refresh(newer)
    session.refresh(older)
    assert result == {"translated": 2, "skipped": 0, "batches_run": 2}
    assert newer.title_zh == "较新的英文标题"
    assert older.title_zh == "较旧的英文标题"
