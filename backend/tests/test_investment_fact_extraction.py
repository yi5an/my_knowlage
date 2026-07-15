"""Tests for investment fact extraction.

Facts are the structured layer between raw investment items and later signal /
thesis workflows. Every generated fact must preserve evidence and confidence.
"""

from __future__ import annotations

from collections.abc import Generator
from uuid import uuid4

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.infrastructure.database import Base
from app.infrastructure.models import (
    Document,
    DocumentChunk,
    DocumentVersion,
    InvestmentClaim,
    InvestmentFact,
    InvestmentItem,
    InvestmentSource,
    InvestmentThesis,
    InvestmentWatchlist,
    TaskJob,
    Video,
    VideoFrameAnalysis,
    Workspace,
)
from app.services.investment.fact_extraction import (
    INVESTMENT_FACT_EXTRACTION_JOB_TYPE,
    InvestmentFactExtractionItem,
    InvestmentFactExtractionSchema,
    InvestmentFactExtractionService,
    InvestmentFactJobHandler,
)
from app.services.structured_output import MockStructuredOutputClient


class RecordingFactClient:
    def __init__(self, output: InvestmentFactExtractionSchema) -> None:
        self.output = output
        self.prompts: list[str] = []

    def generate(self, prompt, schema):  # noqa: ANN001
        self.prompts.append(str(prompt))
        return self.output


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


def _source(session: Session, watchlist_id: str | None = None) -> InvestmentSource:
    source = InvestmentSource(
        id=f"src_{uuid4().hex}",
        workspace_id="ws_default",
        source_type="x_web",
        name="NVIDIA X",
        config={"mode": "account", "username": "nvidia"},
        default_info_layer="opinion",
        default_watchlist_ids=[watchlist_id] if watchlist_id else [],
        poll_interval_seconds=900,
    )
    session.add(source)
    session.commit()
    return source


def _item(session: Session, source: InvestmentSource | None = None) -> InvestmentItem:
    item = InvestmentItem(
        id=f"inv_{uuid4().hex}",
        workspace_id="ws_default",
        source_id=source.id if source else None,
        dedupe_key=f"dk_{uuid4().hex}",
        title="@nvidia: NVIDIA announces a new AI platform",
        source_url="https://x.com/nvidia/status/2075367885438890135",
        source_name="@nvidia",
        summary="NVIDIA announced a new AI platform for data centers.",
        info_layer="opinion",
        source_credibility="personal_opinion",
    )
    session.add(item)
    session.commit()
    return item


def test_extracts_facts_with_evidence_confidence_and_watchlist() -> None:
    session = next(_session())
    watchlist = InvestmentWatchlist(
        id="wl_nvda",
        workspace_id="ws_default",
        name="NVIDIA",
        watch_type="company",
        keywords=["NVIDIA", "AI"],
    )
    session.add(watchlist)
    session.commit()
    source = _source(session, watchlist.id)
    item = _item(session, source)
    canned = InvestmentFactExtractionSchema(
        facts=[
            InvestmentFactExtractionItem(
                fact_text="NVIDIA announced a new AI platform for data centers.",
                fact_text_zh="英伟达宣布面向数据中心的新 AI 平台。",
                fact_type="company_update",
                entities=["NVIDIA", "data centers"],
                evidence_excerpt="NVIDIA announced a new AI platform for data centers.",
                confidence=0.82,
            )
        ]
    )

    result = InvestmentFactExtractionService(
        session=session,
        llm_client=MockStructuredOutputClient(outputs={InvestmentFactExtractionSchema: canned}),
    ).extract_item(item.id)

    assert result["facts_created"] == 1
    fact = session.scalar(select(InvestmentFact))
    assert fact is not None
    assert fact.source_item_id == item.id
    assert fact.watchlist_id == watchlist.id
    assert fact.fact_text_zh == "英伟达宣布面向数据中心的新 AI 平台。"
    assert fact.evidence_url == item.source_url
    assert fact.evidence_excerpt
    assert fact.confidence == 0.82
    assert fact.verification_status == "pending"


def test_youtube_fact_uses_matching_transcript_chunk_timestamp() -> None:
    session = next(_session())
    document = Document(
        id="doc_youtube",
        workspace_id="ws_default",
        title="NVIDIA video",
        source_type="youtube",
        source_uri="https://youtu.be/video123",
        status="ready",
        parse_status="completed",
    )
    version = DocumentVersion(
        id="docver_youtube",
        doc_id=document.id,
        version_no=1,
        title=document.title,
        content_md="[02:05] NVIDIA announced new Blackwell shipments.",
        content_text="[02:05] NVIDIA announced new Blackwell shipments.",
    )
    chunk = DocumentChunk(
        id="chunk_youtube",
        doc_id=document.id,
        version_id=version.id,
        chunk_index=0,
        content="NVIDIA announced new Blackwell shipments during the call.",
        start_offset=125,
        end_offset=160,
        metadata_={},
    )
    item = InvestmentItem(
        id="inv_youtube",
        workspace_id="ws_default",
        document_id=document.id,
        dedupe_key="youtube|doc_youtube",
        title="NVIDIA video",
        source_url="https://youtu.be/video123",
        source_name="YouTube",
        summary="NVIDIA announced new Blackwell shipments during the call.",
        info_layer="opinion",
        source_credibility="personal_opinion",
    )
    session.add_all([document, version, chunk, item])
    session.commit()
    canned = InvestmentFactExtractionSchema(
        facts=[
            InvestmentFactExtractionItem(
                fact_text="NVIDIA announced new Blackwell shipments.",
                fact_type="company_update",
                entities=["NVIDIA", "Blackwell"],
                evidence_excerpt="NVIDIA announced new Blackwell shipments",
                confidence=0.86,
            )
        ]
    )

    InvestmentFactExtractionService(
        session=session,
        llm_client=MockStructuredOutputClient(outputs={InvestmentFactExtractionSchema: canned}),
    ).extract_item(item.id)

    fact = session.scalar(select(InvestmentFact))
    assert fact is not None
    assert fact.evidence_url == "https://youtu.be/video123"
    assert fact.evidence_timestamp == 125


def test_youtube_fact_prompt_includes_transcript_and_visual_ocr() -> None:
    session = next(_session())
    video = Video(
        id="video_prompt",
        workspace_id="ws_default",
        video_id="prompt123",
        title="NVIDIA video",
        fetch_status="fetched",
    )
    document = Document(
        id="doc_prompt",
        workspace_id="ws_default",
        title="NVIDIA video",
        source_type="youtube",
        source_uri="https://youtu.be/prompt123",
        video_id=video.id,
        status="ready",
        parse_status="completed",
        summary_json={
            "tldr": "The video discusses AI capex.",
            "key_points": [{"point": "Blackwell demand is strong.", "timestamp": 30}],
        },
    )
    version = DocumentVersion(
        id="docver_prompt",
        doc_id=document.id,
        version_no=1,
        title=document.title,
        content_md="[00:30] Blackwell demand is strong in data centers.",
        content_text="[00:30] Blackwell demand is strong in data centers.",
    )
    frame = VideoFrameAnalysis(
        id="frame_prompt",
        workspace_id="ws_default",
        video_id=video.id,
        timestamp_sec=42,
        timestamp_str="00:42",
        image_path="/tmp/frame.jpg",
        perceptual_hash="abc",
        frame_type="slide",
        ocr_text="GPU supply chain revenue inflection",
        structured_notes={"title": "GPU supply chain", "bullets": ["revenue inflection"]},
        confidence=0.91,
    )
    item = InvestmentItem(
        id="inv_prompt",
        workspace_id="ws_default",
        document_id=document.id,
        dedupe_key="youtube|doc_prompt",
        title="NVIDIA video",
        source_url="https://youtu.be/prompt123",
        source_name="YouTube",
        summary="The video discusses AI capex.",
        info_layer="opinion",
        source_credibility="personal_opinion",
    )
    session.add_all([video, document, version, frame, item])
    session.commit()
    client = RecordingFactClient(InvestmentFactExtractionSchema(facts=[]))

    InvestmentFactExtractionService(session=session, llm_client=client).extract_item(item.id)

    prompt = client.prompts[0]
    assert "YouTube 总结" in prompt
    assert "Blackwell demand is strong in data centers" in prompt
    assert "视觉资料 OCR" in prompt
    assert "GPU supply chain revenue inflection" in prompt


def test_fact_job_handler_processes_single_item_scope() -> None:
    session = next(_session())
    item = _item(session)
    canned = InvestmentFactExtractionSchema(
        facts=[
            InvestmentFactExtractionItem(
                fact_text="NVIDIA announced a new AI platform.",
                fact_type="company_update",
                entities=["NVIDIA"],
                evidence_excerpt="NVIDIA announced a new AI platform",
                confidence=0.77,
            )
        ]
    )
    job = TaskJob(
        id="job_fact_item",
        workspace_id="ws_default",
        job_type=INVESTMENT_FACT_EXTRACTION_JOB_TYPE,
        target_type="investment_item",
        target_id=item.id,
        status="running",
        input={"workspace_id": "ws_default", "item_id": item.id},
    )
    session.add(job)
    session.commit()

    out = InvestmentFactJobHandler().handle(
        job,
        session,
        MockStructuredOutputClient(outputs={InvestmentFactExtractionSchema: canned}),
    )

    assert out["items_processed"] == 1
    assert out["facts_created"] == 1
    assert session.scalar(select(InvestmentFact).where(InvestmentFact.source_item_id == item.id))


def test_fact_job_creates_idempotent_claim_for_matching_thesis() -> None:
    session = next(_session())
    watchlist = InvestmentWatchlist(
        id="wl_nvda",
        workspace_id="ws_default",
        name="NVIDIA",
        watch_type="company",
        keywords=["NVIDIA", "data center"],
    )
    session.add(watchlist)
    session.add(
        InvestmentThesis(
            id="th_nvda_dc",
            workspace_id="ws_default",
            watchlist_id=watchlist.id,
            title="NVIDIA data center demand remains strong",
            body="Watch whether data center AI platform launches support demand.",
            status="open",
            confidence="medium",
        )
    )
    session.commit()
    source = _source(session, watchlist.id)
    item = _item(session, source)
    canned = InvestmentFactExtractionSchema(
        facts=[
            InvestmentFactExtractionItem(
                fact_text="NVIDIA announced a new AI platform for data centers.",
                fact_text_zh="英伟达宣布面向数据中心的新 AI 平台。",
                fact_type="company_update",
                entities=["NVIDIA", "data centers"],
                evidence_excerpt="NVIDIA announced a new AI platform for data centers.",
                confidence=0.82,
            )
        ]
    )
    job = TaskJob(
        id="job_fact_thesis",
        workspace_id="ws_default",
        job_type=INVESTMENT_FACT_EXTRACTION_JOB_TYPE,
        target_type="investment_item",
        target_id=item.id,
        status="running",
        input={"workspace_id": "ws_default", "item_id": item.id},
    )
    session.add(job)
    session.commit()
    handler = InvestmentFactJobHandler()
    client = MockStructuredOutputClient(outputs={InvestmentFactExtractionSchema: canned})

    handler.handle(job, session, client)
    handler.handle(job, session, client)

    claims = list(session.scalars(select(InvestmentClaim)))
    assert len(claims) == 1
    assert claims[0].source_item_id == item.id
    assert claims[0].watchlist_id == watchlist.id
    assert claims[0].thesis_id == "th_nvda_dc"
    assert claims[0].claim_text == "英伟达宣布面向数据中心的新 AI 平台。"
    assert claims[0].verification_status == "pending"
    assert claims[0].required_evidence == [
        "NVIDIA announced a new AI platform for data centers.",
        item.source_url,
    ]


def test_fact_job_assigns_thesis_impact_to_source_item() -> None:
    session = next(_session())
    watchlist = InvestmentWatchlist(
        id="wl_nvda",
        workspace_id="ws_default",
        name="NVIDIA",
        watch_type="company",
        keywords=["NVIDIA", "data center"],
    )
    session.add(watchlist)
    session.add(
        InvestmentThesis(
            id="th_nvda_demand",
            workspace_id="ws_default",
            watchlist_id=watchlist.id,
            title="NVIDIA data center demand remains strong",
            body="Demand should stay strong and keep growing.",
            status="open",
            confidence="medium",
        )
    )
    session.commit()
    source = _source(session, watchlist.id)
    item = _item(session, source)
    canned = InvestmentFactExtractionSchema(
        facts=[
            InvestmentFactExtractionItem(
                fact_text="NVIDIA data center demand slowed this quarter.",
                fact_text_zh="英伟达数据中心需求本季度放缓。",
                fact_type="company_update",
                entities=["NVIDIA", "data center"],
                evidence_excerpt="NVIDIA data center demand slowed this quarter.",
                confidence=0.84,
            )
        ]
    )
    job = TaskJob(
        id="job_fact_impact",
        workspace_id="ws_default",
        job_type=INVESTMENT_FACT_EXTRACTION_JOB_TYPE,
        target_type="investment_item",
        target_id=item.id,
        status="running",
        input={"workspace_id": "ws_default", "item_id": item.id},
    )
    session.add(job)
    session.commit()

    InvestmentFactJobHandler().handle(
        job,
        session,
        MockStructuredOutputClient(outputs={InvestmentFactExtractionSchema: canned}),
    )

    session.refresh(item)
    assert item.thesis_impact == "unknown"
    assert item.suggested_thesis_impact == "contradicts"


def test_fact_extraction_replaces_existing_item_facts() -> None:
    session = next(_session())
    item = _item(session)
    session.add(
        InvestmentFact(
            id="fact_old",
            workspace_id="ws_default",
            source_item_id=item.id,
            fact_text="old fact",
            fact_type="other",
            entities=[],
            evidence_url=item.source_url,
            evidence_excerpt="old",
            confidence=0.1,
            verification_status="pending",
        )
    )
    session.commit()
    canned = InvestmentFactExtractionSchema(
        facts=[
            InvestmentFactExtractionItem(
                fact_text="new fact",
                fact_type="company_update",
                entities=["NVIDIA"],
                evidence_excerpt="new fact",
                confidence=0.9,
            )
        ]
    )

    InvestmentFactExtractionService(
        session=session,
        llm_client=MockStructuredOutputClient(outputs={InvestmentFactExtractionSchema: canned}),
    ).extract_item(item.id)

    facts = list(session.scalars(select(InvestmentFact)))
    assert len(facts) == 1
    assert facts[0].fact_text == "new fact"
