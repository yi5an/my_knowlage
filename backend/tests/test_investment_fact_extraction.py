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
    EvidenceAnchor,
    InvestmentClaim,
    InvestmentFact,
    InvestmentItem,
    InvestmentSource,
    InvestmentThesis,
    InvestmentWatchlist,
    TaskJob,
    TraceEdge,
    TraceNode,
    Video,
    VideoFrameAnalysis,
    Workspace,
)
from app.schemas.provenance import EvidenceReference
from app.services.investment.fact_extraction import (
    INVESTMENT_FACT_EXTRACTION_JOB_TYPE,
    InvestmentFactExtractionItem,
    InvestmentFactExtractionSchema,
    InvestmentFactExtractionService,
    InvestmentFactJobHandler,
)
from app.services.provenance.links import TraceLinkService
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
                evidence=EvidenceReference(
                    source_segment_id=f"investment_item:{item.id}",
                    quote="NVIDIA announced a new AI platform for data centers.",
                ),
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
                evidence=EvidenceReference(
                    source_segment_id=f"document_chunk:{chunk.id}",
                    quote="NVIDIA announced new Blackwell shipments",
                ),
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
                evidence=EvidenceReference(
                    source_segment_id=f"investment_item:{item.id}",
                    quote="NVIDIA announced a new AI platform",
                ),
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
                evidence=EvidenceReference(
                    source_segment_id=f"investment_item:{item.id}",
                    quote="NVIDIA announced a new AI platform for data centers.",
                ),
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
    item.summary = "NVIDIA data center demand slowed this quarter."
    session.commit()
    canned = InvestmentFactExtractionSchema(
        facts=[
            InvestmentFactExtractionItem(
                fact_text="NVIDIA data center demand slowed this quarter.",
                fact_text_zh="英伟达数据中心需求本季度放缓。",
                fact_type="company_update",
                entities=["NVIDIA", "data center"],
                evidence=EvidenceReference(
                    source_segment_id=f"investment_item:{item.id}",
                    quote="NVIDIA data center demand slowed this quarter.",
                ),
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


def test_identical_rerun_preserves_fact_anchor_node_and_reviewed_edge() -> None:
    session = next(_session())
    item = _item(session)
    canned = InvestmentFactExtractionSchema(
        facts=[
            InvestmentFactExtractionItem(
                fact_text="NVIDIA announced a new AI platform for data centers.",
                fact_type="company_update",
                entities=["NVIDIA"],
                evidence=EvidenceReference(
                    source_segment_id=f"investment_item:{item.id}",
                    quote="NVIDIA announced a new AI platform for data centers.",
                ),
                confidence=0.9,
            )
        ]
    )
    service = InvestmentFactExtractionService(
        session=session,
        llm_client=MockStructuredOutputClient(outputs={InvestmentFactExtractionSchema: canned}),
    )

    first = service.extract_item(item.id)
    fact = session.scalar(select(InvestmentFact).where(InvestmentFact.is_active.is_(True)))
    anchor = session.scalar(select(EvidenceAnchor))
    fact_node = session.scalar(
        select(TraceNode).where(TraceNode.backing_type == "investment_fact")
    )
    edge = session.scalar(select(TraceEdge).where(TraceEdge.relation_type == "derived_from"))
    assert fact is not None and anchor is not None and fact_node is not None and edge is not None
    TraceLinkService(session).review(
        edge_id=edge.id,
        workspace_id="ws_default",
        action="confirm",
        expected_version=edge.version_no,
        reviewer_id="user_1",
        note="checked",
    )
    session.commit()

    second = service.extract_item(item.id)

    rerun_fact = session.scalar(select(InvestmentFact).where(InvestmentFact.is_active.is_(True)))
    rerun_anchor = session.scalar(select(EvidenceAnchor))
    rerun_node = session.scalar(
        select(TraceNode).where(TraceNode.backing_type == "investment_fact")
    )
    rerun_edge = session.scalar(select(TraceEdge).where(TraceEdge.relation_type == "derived_from"))
    assert first == {
        "items_processed": 1,
        "facts_created": 1,
        "facts_reused": 0,
        "facts_skipped": 0,
        "failure_reasons": {},
    }
    assert second == {
        "items_processed": 1,
        "facts_created": 0,
        "facts_reused": 1,
        "facts_skipped": 0,
        "failure_reasons": {},
    }
    assert rerun_fact is not None and rerun_fact.id == fact.id
    assert rerun_anchor is not None and rerun_anchor.id == anchor.id
    assert rerun_node is not None and rerun_node.id == fact_node.id
    assert rerun_edge is not None and rerun_edge.id == edge.id
    assert rerun_edge.review_status == "confirmed"


def test_changed_fact_keeps_inactive_predecessor() -> None:
    session = next(_session())
    item = _item(session)
    item.summary = "Demand was strong. Demand slowed after supply constraints."
    session.commit()
    first_output = InvestmentFactExtractionSchema(
        facts=[
            InvestmentFactExtractionItem(
                fact_text="Demand was strong.",
                fact_type="company_update",
                evidence=EvidenceReference(
                    source_segment_id=f"investment_item:{item.id}",
                    quote="Demand was strong.",
                ),
                confidence=0.8,
            )
        ]
    )
    service = InvestmentFactExtractionService(
        session=session,
        llm_client=MockStructuredOutputClient(
            outputs={InvestmentFactExtractionSchema: first_output}
        ),
    )
    service.extract_item(item.id)
    old = session.scalar(select(InvestmentFact).where(InvestmentFact.is_active.is_(True)))
    assert old is not None
    service.llm_client = MockStructuredOutputClient(
        outputs={
            InvestmentFactExtractionSchema: InvestmentFactExtractionSchema(
                facts=[
                    InvestmentFactExtractionItem(
                        fact_text="Demand slowed after supply constraints.",
                        fact_type="company_update",
                        evidence=EvidenceReference(
                            source_segment_id=f"investment_item:{item.id}",
                            quote="Demand slowed after supply constraints.",
                        ),
                        confidence=0.86,
                    )
                ]
            )
        }
    )

    service.extract_item(item.id)

    facts = list(session.scalars(select(InvestmentFact).order_by(InvestmentFact.created_at)))
    assert len(facts) == 2
    assert facts[0].id == old.id
    assert facts[0].is_active is False
    assert facts[1].is_active is True
    assert facts[1].supersedes_id == old.id


def test_reappearing_fact_reactivates_inactive_row_instead_of_pk_crash() -> None:
    """Regression (2026-09-22 production incident): a fact whose only row is
    inactive (superseded earlier) must be reused, not re-inserted.

    The deterministic id ``fact_{canonical_key[:32]}`` collides with the
    inactive row's primary key, which failed the whole job with
    IntegrityError: duplicate key (investment_fact_pkey)."""
    session = next(_session())
    item = _item(session)
    item.summary = "Demand was strong. Demand slowed after supply constraints."
    session.commit()

    def output_with(text: str) -> MockStructuredOutputClient:
        return MockStructuredOutputClient(
            outputs={
                InvestmentFactExtractionSchema: InvestmentFactExtractionSchema(
                    facts=[
                        InvestmentFactExtractionItem(
                            fact_text=text,
                            fact_type="company_update",
                            evidence=EvidenceReference(
                                source_segment_id=f"investment_item:{item.id}",
                                quote=text,
                            ),
                            confidence=0.8,
                        )
                    ]
                )
            }
        )

    service = InvestmentFactExtractionService(
        session=session,
        llm_client=output_with("Demand was strong."),
    )
    service.extract_item(item.id)

    # Second extraction returns only the changed fact -> first becomes inactive.
    service.llm_client = output_with("Demand slowed after supply constraints.")
    service.extract_item(item.id)
    inactive = session.scalar(
        select(InvestmentFact).where(InvestmentFact.fact_text == "Demand was strong.")
    )
    assert inactive is not None and inactive.is_active is False

    # Third extraction returns the ORIGINAL fact again. Before the fix this
    # raised IntegrityError (duplicate investment_fact_pkey); afterwards the
    # inactive row is reused and reactivated.
    service.llm_client = output_with("Demand was strong.")
    service.extract_item(item.id)

    facts = list(session.scalars(select(InvestmentFact)))
    assert len(facts) == 2
    reactivated = [
        f for f in facts if f.fact_text == "Demand was strong."
    ]
    assert len(reactivated) == 1
    assert reactivated[0].id == inactive.id
    assert reactivated[0].is_active is True


def test_fabricated_evidence_is_skipped_with_reason() -> None:
    session = next(_session())
    item = _item(session)
    canned = InvestmentFactExtractionSchema(
        facts=[
            InvestmentFactExtractionItem(
                fact_text="NVIDIA secretly doubled revenue.",
                fact_type="company_update",
                evidence=EvidenceReference(
                    source_segment_id=f"investment_item:{item.id}",
                    quote="secretly doubled revenue",
                ),
                confidence=0.9,
            )
        ]
    )

    result = InvestmentFactExtractionService(
        session=session,
        llm_client=MockStructuredOutputClient(outputs={InvestmentFactExtractionSchema: canned}),
    ).extract_item(item.id)

    assert result["facts_created"] == 0
    assert result["facts_skipped"] == 1
    assert result["failure_reasons"] == {"evidence_quote_mismatch": 1}
    assert session.scalar(select(InvestmentFact)) is None


def test_frame_reference_creates_image_region_anchor() -> None:
    session = next(_session())
    video = Video(
        id="video_frame_anchor",
        workspace_id="ws_default",
        video_id="frame-anchor",
        title="Frame anchor",
        fetch_status="fetched",
    )
    document = Document(
        id="doc_frame_anchor",
        workspace_id="ws_default",
        title="Frame anchor",
        source_type="youtube",
        source_uri="https://youtu.be/frame-anchor",
        video_id=video.id,
        status="ready",
        parse_status="completed",
    )
    version = DocumentVersion(
        id="docver_frame_anchor",
        doc_id=document.id,
        version_no=1,
        title=document.title,
        content_md="Frame transcript",
        content_text="Frame transcript",
    )
    frame = VideoFrameAnalysis(
        id="frame_anchor",
        workspace_id="ws_default",
        video_id=video.id,
        timestamp_sec=42,
        timestamp_str="00:42",
        image_path="/tmp/frame-anchor.jpg",
        perceptual_hash="frame-anchor",
        frame_type="slide",
        ocr_text="GPU supply chain revenue inflection",
        confidence=0.91,
    )
    item = InvestmentItem(
        id="inv_frame_anchor",
        workspace_id="ws_default",
        document_id=document.id,
        dedupe_key="youtube|frame-anchor",
        title="Frame anchor",
        source_url=document.source_uri,
        source_name="YouTube",
        summary="A supply-chain slide is shown.",
        info_layer="opinion",
        source_credibility="personal_opinion",
    )
    session.add_all([video, document, version, frame, item])
    session.commit()
    canned = InvestmentFactExtractionSchema(
        facts=[
            InvestmentFactExtractionItem(
                fact_text="The slide shows a GPU supply chain revenue inflection.",
                fact_type="company_update",
                evidence=EvidenceReference(
                    source_segment_id=f"video_frame_analysis:{frame.id}",
                    quote="GPU supply chain revenue inflection",
                    bbox=(0.1, 0.2, 0.9, 0.8),
                    ocr_block_ids=["ocr_1"],
                ),
                confidence=0.88,
            )
        ]
    )

    InvestmentFactExtractionService(
        session=session,
        llm_client=MockStructuredOutputClient(outputs={InvestmentFactExtractionSchema: canned}),
    ).extract_item(item.id)

    anchor = session.scalar(select(EvidenceAnchor))
    assert anchor is not None
    assert anchor.anchor_type == "image_region"
    assert anchor.locator == {
        "type": "image_region",
        "frame_id": frame.id,
        "bbox": [0.1, 0.2, 0.9, 0.8],
        "ocr_block_ids": ["ocr_1"],
    }


def test_youtube_timestamp_creates_media_segment_anchor() -> None:
    session = next(_session())
    document = Document(
        id="doc_media_anchor",
        workspace_id="ws_default",
        title="Media anchor",
        source_type="youtube",
        source_uri="https://youtu.be/media-anchor",
        status="ready",
        parse_status="completed",
    )
    version = DocumentVersion(
        id="docver_media_anchor",
        doc_id=document.id,
        version_no=1,
        title=document.title,
        content_md="Blackwell demand remained strong.",
        content_text="Blackwell demand remained strong.",
    )
    chunk = DocumentChunk(
        id="chunk_media_anchor",
        doc_id=document.id,
        version_id=version.id,
        chunk_index=0,
        content="Blackwell demand remained strong.",
        start_offset=125,
        end_offset=160,
        metadata_={},
    )
    item = InvestmentItem(
        id="inv_media_anchor",
        workspace_id="ws_default",
        document_id=document.id,
        dedupe_key="youtube|media-anchor",
        title="Media anchor",
        source_url=document.source_uri,
        source_name="YouTube",
        summary="Blackwell demand remained strong.",
        info_layer="opinion",
        source_credibility="personal_opinion",
    )
    session.add_all([document, version, chunk, item])
    session.commit()
    canned = InvestmentFactExtractionSchema(
        facts=[
            InvestmentFactExtractionItem(
                fact_text="Blackwell demand remained strong.",
                fact_type="company_update",
                evidence=EvidenceReference(
                    source_segment_id=f"document_chunk:{chunk.id}",
                    quote="Blackwell demand remained strong.",
                ),
                confidence=0.86,
            )
        ]
    )

    InvestmentFactExtractionService(
        session=session,
        llm_client=MockStructuredOutputClient(outputs={InvestmentFactExtractionSchema: canned}),
    ).extract_item(item.id)

    anchor = session.scalar(select(EvidenceAnchor))
    assert anchor is not None
    assert anchor.anchor_type == "media_segment"
    assert anchor.locator["start_ms"] == 125_000
    assert anchor.locator["end_ms"] == 160_000
