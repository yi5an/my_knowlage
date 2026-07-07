"""Tests for investment-item translation (service + job handler + fetch enqueue).

Uses ``MockStructuredOutputClient`` to feed canned translations. Verifies:
- English items get title_zh/summary_zh written from the LLM output.
- Already-Chinese items are skipped (title_zh set to original, no LLM call).
- Already-translated items (title_zh not null) are not re-queried.
- LLM failure / no-client degrades gracefully (original text kept, no raise).
- A successful fetch enqueues an ``investment_translation`` job (exactly one).
"""

from __future__ import annotations

from collections.abc import Generator
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.infrastructure.database import Base
from app.infrastructure.models import InvestmentItem, InvestmentSource, TaskJob, Workspace
from app.schemas.investment import (
    InvestmentTranslationItem,
    InvestmentTranslationSchema,
)
from app.services.investment.fetch_job_handler import (
    INVESTMENT_CLASSIFICATION_JOB_TYPE,
    INVESTMENT_FETCH_JOB_TYPE,
    INVESTMENT_TRANSLATION_JOB_TYPE,
    InvestmentFetchJobHandler,
)
from app.services.investment.fetchers import InvestmentRawItem
from app.services.investment.translation import InvestmentTranslationService
from app.services.investment.translation_job_handler import (
    InvestmentTranslationJobHandler,
)
from app.services.structured_output import MockStructuredOutputClient


@pytest.fixture()
def session() -> Generator[Session, None, None]:
    eng = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(bind=eng)
    sm = sessionmaker(bind=eng, expire_on_commit=False)
    with sm() as s:
        s.add(Workspace(id="ws_default", name="Default"))
        s.commit()
        yield s


def _make_item(
    session: Session,
    title: str,
    summary: str | None = None,
    item_id: str | None = None,
    title_zh: str | None = None,
    summary_zh: str | None = None,
) -> InvestmentItem:
    item = InvestmentItem(
        id=item_id or f"inv_{uuid4().hex}",
        workspace_id="ws_default",
        title=title,
        summary=summary,
        info_layer="macro_calendar",
        source_credibility="official",
        dedupe_key=f"dk_{uuid4().hex}",
        title_zh=title_zh,
        summary_zh=summary_zh,
    )
    session.add(item)
    session.commit()
    return item


# --- service ---------------------------------------------------------------


def test_translates_english_items_from_llm_output(session: Session):
    en = _make_item(session, "Federal Reserve issues FOMC statement", "rate decision")
    canned = InvestmentTranslationSchema(
        translations=[
            InvestmentTranslationItem(
                item_id=en.id, title_zh="美联储发布FOMC声明", summary_zh="利率决议"
            )
        ]
    )
    client = MockStructuredOutputClient(outputs={InvestmentTranslationSchema: canned})
    result = InvestmentTranslationService(
        session=session, llm_client=client
    ).translate_untranslated()

    assert result["translated"] == 1
    session.refresh(en)
    assert en.title_zh == "美联储发布FOMC声明"
    assert en.summary_zh == "利率决议"


def test_skips_already_chinese_items_without_llm_call(session: Session):
    zh = _make_item(session, "美联储发布利率决议", "今日维持利率不变")
    # No output registered for the schema -> if the service called the LLM,
    # MockStructuredOutputClient would raise. Passing None client makes the
    # skip explicit.
    result = InvestmentTranslationService(session=session, llm_client=None).translate_untranslated()

    assert result["translated"] == 0
    assert result["skipped"] == 1
    session.refresh(zh)
    # Already-Chinese items get title_zh set to the original (so they're not re-queried).
    assert zh.title_zh == "美联储发布利率决议"


def test_does_not_requery_already_translated_items(session: Session):
    # title_zh and summary_zh already set → not picked up by translate_untranslated.
    _make_item(session, "already done", "done summary", title_zh="已翻译", summary_zh="已翻译摘要")
    _make_item(session, "needs translation")

    # No client: the "needs translation" (English) item is in the to_translate
    # bucket but with no client the service returns translated=0. The
    # pre-translated item is never queried at all.
    result = InvestmentTranslationService(
        session=session, llm_client=None
    ).translate_untranslated()
    assert result["translated"] == 0


def test_retranslates_summary_when_refetch_clears_summary_zh(session: Session):
    item = _make_item(
        session,
        "Federal Reserve issues FOMC statement",
        "The Committee decided to maintain the target range.",
        title_zh="美联储发布FOMC声明",
        summary_zh=None,
    )
    canned = InvestmentTranslationSchema(
        translations=[
            InvestmentTranslationItem(
                item_id=item.id,
                title_zh="美联储发布FOMC声明",
                summary_zh="委员会决定维持目标区间。",
            )
        ]
    )
    client = MockStructuredOutputClient(outputs={InvestmentTranslationSchema: canned})

    result = InvestmentTranslationService(
        session=session, llm_client=client
    ).translate_untranslated()

    assert result["translated"] == 1
    session.refresh(item)
    assert item.title_zh == "美联储发布FOMC声明"
    assert item.summary_zh == "委员会决定维持目标区间。"


def test_llm_failure_degrades_gracefully(session: Session):
    _make_item(session, "Some English title", "summary")

    class _BoomClient:
        def generate(self, prompt, schema):  # noqa: ANN001
            raise RuntimeError("LLM is down")

    result = InvestmentTranslationService(
        session=session, llm_client=_BoomClient()  # type: ignore[arg-type]
    ).translate_untranslated()
    assert result["translated"] == 0
    # original title/summary untouched
    item = session.scalar(select(InvestmentItem))
    assert item.title_zh is None


def test_llm_failure_can_be_raised_for_user_visible_retry(session: Session):
    _make_item(session, "Some English title", "summary")

    class _BoomClient:
        def generate(self, prompt, schema):  # noqa: ANN001
            raise RuntimeError("LLM is down")

    with pytest.raises(RuntimeError, match="investment translation failed"):
        InvestmentTranslationService(
            session=session, llm_client=_BoomClient()  # type: ignore[arg-type]
        ).translate_untranslated(raise_on_failure=True)

    item = session.scalar(select(InvestmentItem))
    assert item.title_zh is None


# --- job handler -----------------------------------------------------------


def test_translation_handler_uses_llm_client(session: Session):
    en = _make_item(session, "FOMC statement", "rate held")
    canned = InvestmentTranslationSchema(
        translations=[
            InvestmentTranslationItem(
                item_id=en.id, title_zh="FOMC声明", summary_zh="维持利率"
            )
        ]
    )
    client = MockStructuredOutputClient(outputs={InvestmentTranslationSchema: canned})
    job = TaskJob(
        id="job_t1",
        workspace_id="ws_default",
        job_type=INVESTMENT_TRANSLATION_JOB_TYPE,
        target_type="investment_source",
        target_id="src_x",
        status="running",
        input={"source_id": "src_x", "workspace_id": "ws_default"},
    )
    session.add(job)
    session.commit()

    out = InvestmentTranslationJobHandler().handle(job, session, client)
    assert out["translated"] == 1
    session.refresh(en)
    assert en.title_zh == "FOMC声明"


def test_translation_handler_raises_when_llm_fails(session: Session):
    _make_item(session, "FOMC statement", "rate held")

    class _BoomClient:
        def generate(self, prompt, schema):  # noqa: ANN001
            raise RuntimeError("LLM is down")

    job = TaskJob(
        id="job_t_fail",
        workspace_id="ws_default",
        job_type=INVESTMENT_TRANSLATION_JOB_TYPE,
        target_type="investment_source",
        target_id="src_x",
        status="running",
        input={"source_id": "src_x", "workspace_id": "ws_default"},
    )
    session.add(job)
    session.commit()

    with pytest.raises(RuntimeError, match="investment translation failed"):
        InvestmentTranslationJobHandler().handle(
            job, session, _BoomClient()  # type: ignore[arg-type]
        )


# --- fetch handler enqueues translation -----------------------------------


class _FakeHttp:
    def get(self, url, headers=None):  # noqa: ANN001
        return (
            b"<rss><channel>"
            b'<item><title>Fed cut rates</title><link>https://x/a</link>'
            b"<guid>https://x/a</guid><description>lowered by 25bps</description></item>"
            b"</channel></rss>"
        ), url

    def close(self):
        pass


def test_successful_fetch_enqueues_translation_and_classification_jobs(session: Session):
    src = InvestmentSource(
        id="src_t",
        workspace_id="ws_default",
        source_type="rss",
        name="Test RSS",
        url="https://x/feed.xml",
        default_info_layer="macro_calendar",
        enabled=True,
    )
    session.add(src)
    job = TaskJob(
        id="job_f1",
        workspace_id="ws_default",
        job_type=INVESTMENT_FETCH_JOB_TYPE,
        target_type="investment_source",
        target_id=src.id,
        status="running",
        input={"source_id": src.id},
    )
    session.add(job)
    session.commit()

    InvestmentFetchJobHandler(http_client=_FakeHttp()).handle(job, session, llm_client=None)

    translation_jobs = list(
        session.scalars(
            select(TaskJob).where(TaskJob.job_type == INVESTMENT_TRANSLATION_JOB_TYPE)
        )
    )
    assert len(translation_jobs) == 1
    assert translation_jobs[0].status == "pending"
    assert translation_jobs[0].input["source_id"] == src.id
    classification_jobs = list(
        session.scalars(
            select(TaskJob).where(TaskJob.job_type == INVESTMENT_CLASSIFICATION_JOB_TYPE)
        )
    )
    assert len(classification_jobs) == 1
    assert classification_jobs[0].status == "pending"
    assert classification_jobs[0].input["source_id"] == src.id


def test_fetch_does_not_duplicate_translation_job(session: Session):
    src = InvestmentSource(
        id="src_t2",
        workspace_id="ws_default",
        source_type="rss",
        name="Test RSS 2",
        url="https://x/feed2.xml",
        default_info_layer="macro_calendar",
        enabled=True,
    )
    session.add(src)
    # Pre-existing pending translation job for this workspace.
    session.add(
        TaskJob(
            id="job_existing_t",
            workspace_id="ws_default",
            job_type=INVESTMENT_TRANSLATION_JOB_TYPE,
            target_type="investment_source",
            target_id=src.id,
            status="pending",
            input={"source_id": src.id, "workspace_id": "ws_default"},
        )
    )
    job = TaskJob(
        id="job_f2",
        workspace_id="ws_default",
        job_type=INVESTMENT_FETCH_JOB_TYPE,
        target_type="investment_source",
        target_id=src.id,
        status="running",
        input={"source_id": src.id},
    )
    session.add(job)
    session.commit()

    InvestmentFetchJobHandler(http_client=_FakeHttp()).handle(job, session, llm_client=None)

    translation_jobs = list(
        session.scalars(
            select(TaskJob).where(TaskJob.job_type == INVESTMENT_TRANSLATION_JOB_TYPE)
        )
    )
    assert len(translation_jobs) == 1  # the pre-existing one, no duplicate


def test_dedupe_fetch_enqueues_translation_for_existing_untranslated_items(
    session: Session,
):
    src = InvestmentSource(
        id="src_existing_untranslated",
        workspace_id="ws_default",
        source_type="rss",
        name="Existing RSS",
        url="https://x/existing.xml",
        default_info_layer="macro_calendar",
        enabled=True,
    )
    session.add(src)
    job = TaskJob(
        id="job_existing_fetch",
        workspace_id="ws_default",
        job_type=INVESTMENT_FETCH_JOB_TYPE,
        target_type="investment_source",
        target_id=src.id,
        status="running",
        input={"source_id": src.id},
    )
    session.add(job)
    session.commit()

    handler = InvestmentFetchJobHandler(http_client=_FakeHttp())
    handler.handle(job, session, llm_client=None)
    session.execute(
        TaskJob.__table__.delete().where(
            TaskJob.job_type.in_(
                [INVESTMENT_TRANSLATION_JOB_TYPE, INVESTMENT_CLASSIFICATION_JOB_TYPE]
            )
        )
    )
    session.commit()

    output = handler.handle(job, session, llm_client=None)

    assert output["items_created"] == 0
    assert output["items_skipped"] == 1
    translation_jobs = list(
        session.scalars(
            select(TaskJob).where(TaskJob.job_type == INVESTMENT_TRANSLATION_JOB_TYPE)
        )
    )
    assert len(translation_jobs) == 1
    assert translation_jobs[0].status == "pending"


def _raw_item() -> InvestmentRawItem:
    return InvestmentRawItem(
        external_id="x",
        title="Fed cut rates",
        url="https://x/a",
        source_name="Test",
        published_at=None,
        summary="lowered by 25bps",
        raw_payload={},
    )
