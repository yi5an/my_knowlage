"""Evidence-backed fact extraction for investment items."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.infrastructure.models import (
    Document,
    DocumentChunk,
    DocumentVersion,
    EvidenceAnchor,
    InvestmentFact,
    InvestmentItem,
    InvestmentSource,
    TaskJob,
    VideoFrameAnalysis,
)
from app.schemas.provenance import (
    EvidenceAnchorCreate,
    EvidenceAnchorType,
    EvidenceLocator,
    EvidenceReference,
    ImageRegionLocator,
    MediaSegmentLocator,
    OriginType,
    PdfRegionLocator,
    TextSpanLocator,
    WebFragmentLocator,
)
from app.services.investment.hypothesis_matcher import InvestmentHypothesisMatcher
from app.services.investment.signal_service import InvestmentSignalService
from app.services.provenance.evidence import EvidenceAnchorService
from app.services.provenance.links import TraceLinkService
from app.services.provenance.registry import TraceRegistrationService
from app.services.structured_output import StructuredOutputClient

logger = logging.getLogger(__name__)

INVESTMENT_FACT_EXTRACTION_JOB_TYPE = "investment_fact_extract"


class InvestmentFactExtractionItem(BaseModel):
    fact_text: str = Field(min_length=1)
    fact_text_zh: str | None = None
    fact_type: str = Field(default="other")
    entities: list[str] = Field(default_factory=list)
    evidence_url: str | None = None
    evidence: EvidenceReference | None = None
    # Legacy fields remain source-compatible for existing providers. New
    # prompts return ``evidence`` and the service resolves legacy excerpts only
    # when they map uniquely to a persisted segment.
    evidence_excerpt: str | None = Field(default=None, min_length=1)
    evidence_timestamp: int | None = None
    confidence: float = Field(ge=0, le=1)


class InvestmentFactExtractionSchema(BaseModel):
    facts: list[InvestmentFactExtractionItem] = Field(default_factory=list, max_length=10)


SYSTEM_RULES = """你是投资研究事实抽取助手。规则：
1. 只抽取文本中明确出现的信息，不补充外部知识。
2. 观点、预测、传闻也可以抽取，但 fact_type 必须标明 opinion/prediction/rumor。
3. 每条事实必须带 evidence.source_segment_id、evidence.quote 和 confidence。
4. source_segment_id 只能使用下方列出的持久化来源片段 ID，quote 必须逐字复制。
5. 如果不能从片段找到证据，不要输出该事实。
6. 最多输出 10 条高价值事实，严格输出 JSON。"""


@dataclass(frozen=True)
class _FactSourceSegment:
    id: str
    text: str
    document_id: str | None = None
    version_id: str | None = None
    chunk_id: str | None = None
    frame_id: str | None = None
    locator: EvidenceLocator | None = None
    published_at: datetime | None = None


@dataclass(frozen=True)
class _ResolvedFactEvidence:
    segment: _FactSourceSegment
    locator: EvidenceLocator
    quote: str
    evidence_timestamp: int | None


def _build_prompt(
    item: InvestmentItem,
    extra_context: str = "",
    segments: list[_FactSourceSegment] | None = None,
) -> str:
    text_parts = [item.title]
    if item.summary:
        text_parts.append(item.summary)
    if item.title_zh and item.title_zh != item.title:
        text_parts.append(f"中文标题: {item.title_zh}")
    if item.summary_zh and item.summary_zh != item.summary:
        text_parts.append(f"中文摘要: {item.summary_zh}")
    text = "\n".join(part for part in text_parts if part)
    if extra_context:
        text = f"{text}\n\n{extra_context}"
    segment_text = "\n\n".join(
        f"[{segment.id}]\n{segment.text}" for segment in (segments or []) if segment.text
    )
    return (
        f"{SYSTEM_RULES}\n\n"
        f"信息层级: {item.info_layer}\n"
        f"来源可信度: {item.source_credibility}\n"
        f"来源名称: {item.source_name or '未知'}\n"
        f"来源链接: {item.source_url or '无'}\n\n"
        f"文本:\n{text}\n\n"
        f"可引用的持久化来源片段:\n{segment_text or '无'}\n\n"
        "请抽取事实点。"
    )


class InvestmentFactExtractionService:
    def __init__(self, session: Session, llm_client: StructuredOutputClient) -> None:
        self.session = session
        self.llm_client = llm_client

    def extract_item(self, item_id: str) -> dict[str, Any]:
        item = self.session.get(InvestmentItem, item_id)
        if item is None:
            raise ValueError(f"investment item {item_id!r} not found")

        segments = self._source_segments(item)
        result = self.llm_client.generate(
            _build_prompt(item, self._youtube_extra_context(item), segments),
            InvestmentFactExtractionSchema,
        )
        watchlist_id = self._infer_watchlist_id(item)
        created = 0
        reused = 0
        skipped = 0
        failure_reasons: dict[str, int] = {}
        seen_keys: set[str] = set()
        prior_active_facts = list(
            self.session.scalars(
                select(InvestmentFact).where(
                    InvestmentFact.workspace_id == item.workspace_id,
                    InvestmentFact.source_item_id == item.id,
                    InvestmentFact.is_active.is_(True),
                )
            )
        )
        used_predecessors: set[str] = set()
        for fact in result.facts[:10]:
            try:
                with self.session.begin_nested():
                    resolved = self._resolve_evidence(item, fact, segments)
                    if resolved is None:
                        raise _FactSkip("evidence_quote_mismatch")
                    fact_text = fact.fact_text.strip()
                    if not fact_text:
                        raise _FactSkip("empty_fact_text")
                    anchor = self._ensure_anchor(item, resolved)
                    canonical_key = _fact_key(item.id, anchor.id, fact_text)
                    if canonical_key in seen_keys:
                        raise _FactSkip("duplicate_fact")
                    seen_keys.add(canonical_key)
                    existing = self.session.scalar(
                        select(InvestmentFact).where(
                            InvestmentFact.workspace_id == item.workspace_id,
                            InvestmentFact.canonical_key == canonical_key,
                            InvestmentFact.is_active.is_(True),
                        )
                    )
                    if existing is not None:
                        self._update_fact(
                            existing,
                            item=item,
                            watchlist_id=watchlist_id,
                            extraction=fact,
                            resolved=resolved,
                        )
                        self._ensure_trace(existing, anchor, fact_text)
                        reused += 1
                        continue
                    predecessor = next(
                        (
                            old_fact
                            for old_fact in prior_active_facts
                            if old_fact.id not in used_predecessors
                            and old_fact.canonical_key not in seen_keys
                        ),
                        None,
                    )
                    if predecessor is not None:
                        used_predecessors.add(predecessor.id)
                    new_fact = InvestmentFact(
                        id=f"fact_{canonical_key[:32]}",
                        workspace_id=item.workspace_id,
                        source_item_id=item.id,
                        watchlist_id=watchlist_id,
                        fact_text=fact_text,
                        fact_text_zh=fact.fact_text_zh.strip() if fact.fact_text_zh else None,
                        fact_type=fact.fact_type.strip() or "other",
                        entities=[str(entity) for entity in fact.entities if str(entity).strip()],
                        evidence_url=fact.evidence_url or item.source_url,
                        evidence_excerpt=resolved.quote,
                        evidence_timestamp=resolved.evidence_timestamp,
                        confidence=float(fact.confidence),
                        verification_status="pending",
                        canonical_key=canonical_key,
                        is_active=True,
                        supersedes_id=predecessor.id if predecessor else None,
                    )
                    self.session.add(new_fact)
                    self.session.flush()
                    self._ensure_trace(new_fact, anchor, fact_text)
                    created += 1
            except _FactSkip as exc:
                skipped += 1
                failure_reasons[exc.reason] = failure_reasons.get(exc.reason, 0) + 1
            except (AppError, ValueError) as exc:
                skipped += 1
                reason = _failure_reason(exc)
                failure_reasons[reason] = failure_reasons.get(reason, 0) + 1

        # Facts not returned by the current extraction are historical, not
        # deletions. Keeping them inactive preserves audit and review links.
        if seen_keys:
            for old_fact in prior_active_facts:
                if old_fact.canonical_key not in seen_keys:
                    old_fact.is_active = False
        self.session.commit()
        logger.info(
            "investment fact extraction: item %s -> created=%d reused=%d skipped=%d",
            item.id,
            created,
            reused,
            skipped,
        )
        return {
            "items_processed": 1,
            "facts_created": created,
            "facts_reused": reused,
            "facts_skipped": skipped,
            "failure_reasons": failure_reasons,
        }

    def _ensure_anchor(
        self, item: InvestmentItem, resolved: _ResolvedFactEvidence
    ) -> EvidenceAnchor:
        segment = resolved.segment
        request = EvidenceAnchorCreate(
            document_id=segment.document_id,
            version_id=segment.version_id,
            source_item_id=item.id if segment.id.startswith("investment_item:") else None,
            anchor_type=EvidenceAnchorType(resolved.locator.type),
            locator=resolved.locator,
            quote=resolved.quote,
            source_uri_snapshot=item.source_url,
            source_quality=float(item.source_credibility == "official") or None,
            created_by_type=OriginType.ai,
            created_by_id=item.id,
        )
        return EvidenceAnchorService(self.session).create(
            workspace_id=item.workspace_id,
            request=request,
        )

    def _ensure_trace(
        self, fact: InvestmentFact, anchor: EvidenceAnchor, fact_text: str
    ) -> None:
        registry = TraceRegistrationService(self.session)
        evidence_node = registry.register(
            workspace_id=fact.workspace_id,
            backing_type="evidence_anchor",
            backing_id=anchor.id,
            layer="evidence",
            node_type=anchor.anchor_type,
            label=anchor.quote[:240],
            display_status=anchor.validation_state,
            confidence=anchor.source_quality,
            properties={"source_item_id": fact.source_item_id},
        )
        fact_node = registry.register(
            workspace_id=fact.workspace_id,
            backing_type="investment_fact",
            backing_id=fact.id,
            layer="event",
            node_type="fact",
            label=fact_text[:240],
            display_status=fact.verification_status,
            confidence=fact.confidence,
            occurred_at=None,
            properties={"canonical_key": fact.canonical_key, "is_active": fact.is_active},
        )
        TraceLinkService(self.session).create(
            workspace_id=fact.workspace_id,
            source_node_id=evidence_node.id,
            target_node_id=fact_node.id,
            relation_type="derived_from",
            origin_type="ai",
            confidence=fact.confidence,
            rationale="Fact was extracted from an exact persisted source quote.",
            evidence_anchor_ids=[anchor.id],
            model_metadata={"workflow": INVESTMENT_FACT_EXTRACTION_JOB_TYPE},
        )

    def _update_fact(
        self,
        existing: InvestmentFact,
        *,
        item: InvestmentItem,
        watchlist_id: str | None,
        extraction: InvestmentFactExtractionItem,
        resolved: _ResolvedFactEvidence,
    ) -> None:
        existing.watchlist_id = watchlist_id
        existing.fact_text_zh = extraction.fact_text_zh.strip() if extraction.fact_text_zh else None
        existing.fact_type = extraction.fact_type.strip() or "other"
        existing.entities = [str(entity) for entity in extraction.entities if str(entity).strip()]
        existing.evidence_url = extraction.evidence_url or item.source_url
        existing.evidence_excerpt = resolved.quote
        existing.evidence_timestamp = resolved.evidence_timestamp
        existing.confidence = float(extraction.confidence)

    def _source_segments(self, item: InvestmentItem) -> list[_FactSourceSegment]:
        segments: list[_FactSourceSegment] = []
        item_text = _investment_item_text(item)
        if item_text:
            segments.append(
                _FactSourceSegment(
                    id=f"investment_item:{item.id}",
                    text=item_text,
                    published_at=item.published_at or item.event_at or item.created_at,
                )
            )
        if not item.document_id:
            return segments
        document = self.session.get(Document, item.document_id)
        if document is None or document.workspace_id != item.workspace_id:
            return segments
        chunks = list(
            self.session.scalars(
                select(DocumentChunk)
                .where(DocumentChunk.doc_id == document.id)
                .order_by(DocumentChunk.chunk_index)
            )
        )
        for chunk in chunks:
            segments.append(
                _FactSourceSegment(
                    id=f"document_chunk:{chunk.id}",
                    text=chunk.content,
                    document_id=document.id,
                    version_id=chunk.version_id,
                    chunk_id=chunk.id,
                    published_at=item.published_at or item.event_at,
                )
            )
        if document.video_id:
            frames = list(
                self.session.scalars(
                    select(VideoFrameAnalysis)
                    .where(
                        VideoFrameAnalysis.video_id == document.video_id,
                        VideoFrameAnalysis.workspace_id == item.workspace_id,
                    )
                    .order_by(VideoFrameAnalysis.timestamp_sec)
                    .limit(20)
                )
            )
            latest_version = self.session.scalar(
                select(DocumentVersion)
                .where(DocumentVersion.doc_id == document.id)
                .order_by(DocumentVersion.version_no.desc())
            )
            for frame in frames:
                frame_text = "\n".join(
                    value
                    for value in [
                        frame.ocr_text,
                        _compact_json_text(frame.structured_notes or {}),
                    ]
                    if value
                )
                if frame_text:
                    segments.append(
                        _FactSourceSegment(
                            id=f"video_frame_analysis:{frame.id}",
                            text=frame_text,
                            document_id=document.id,
                            version_id=latest_version.id if latest_version else None,
                            frame_id=frame.id,
                            published_at=item.published_at or item.event_at,
                        )
                    )
        return segments

    def _resolve_evidence(
        self,
        item: InvestmentItem,
        extraction: InvestmentFactExtractionItem,
        segments: list[_FactSourceSegment],
    ) -> _ResolvedFactEvidence | None:
        reference = extraction.evidence
        if reference is None:
            quote = (extraction.evidence_excerpt or "").strip()
            if not quote:
                return None
            matches = [segment for segment in segments if quote in segment.text]
            if len(matches) != 1:
                return None
            reference = EvidenceReference(
                source_segment_id=matches[0].id,
                quote=quote,
                start_offset=matches[0].text.find(quote),
                end_offset=matches[0].text.find(quote) + len(quote),
            )
        if reference.anchor_id:
            anchor = self.session.get(EvidenceAnchor, reference.anchor_id)
            if anchor is None or anchor.workspace_id != item.workspace_id:
                return None
            if anchor.quote != reference.quote:
                return None
            locator = _locator_from_anchor(anchor)
            segment = _FactSourceSegment(
                id=f"anchor:{anchor.id}",
                text=anchor.quote,
                document_id=anchor.document_id,
                version_id=anchor.version_id,
                chunk_id=anchor.chunk_id,
                frame_id=(anchor.locator or {}).get("frame_id"),
            )
            return _ResolvedFactEvidence(
                segment=segment,
                locator=locator,
                quote=anchor.quote,
                evidence_timestamp=_timestamp_from_locator(locator),
            )
        segment_id = reference.source_segment_id
        source_segment = next((value for value in segments if value.id == segment_id), None)
        if source_segment is None or reference.quote not in source_segment.text:
            return None
        start = (
            reference.start_offset
            if reference.start_offset is not None
            else source_segment.text.find(reference.quote)
        )
        end = start + len(reference.quote)
        if start < 0 or source_segment.text[start:end] != reference.quote:
            return None
        candidate_locator = self._segment_locator(
            item, source_segment, reference, start, end
        )
        if candidate_locator is None:
            return None
        locator = candidate_locator
        timestamp = extraction.evidence_timestamp
        if timestamp is None:
            timestamp = _timestamp_from_locator(locator)
        return _ResolvedFactEvidence(
            segment=source_segment,
            locator=locator,
            quote=reference.quote,
            evidence_timestamp=timestamp,
        )

    def _segment_locator(
        self,
        item: InvestmentItem,
        segment: _FactSourceSegment,
        reference: EvidenceReference,
        start: int,
        end: int,
    ) -> EvidenceLocator | None:
        if segment.id.startswith("investment_item:"):
            return WebFragmentLocator(
                fragment_id=item.id,
                text_quote=reference.quote,
                captured_at=item.published_at
                or item.event_at
                or item.created_at
                or datetime.now(UTC),
            )
        if segment.frame_id:
            if reference.bbox is None:
                return None
            return ImageRegionLocator(
                frame_id=segment.frame_id,
                bbox=reference.bbox,
                ocr_block_ids=reference.ocr_block_ids,
            )
        chunk = self.session.get(DocumentChunk, segment.chunk_id) if segment.chunk_id else None
        document = self.session.get(Document, segment.document_id) if segment.document_id else None
        if chunk is None or document is None:
            return None
        if document.source_type == "youtube":
            start_sec = chunk.start_offset
            end_sec = chunk.end_offset
            if reference.start_ms is not None and reference.end_ms is not None:
                return MediaSegmentLocator(
                    start_ms=reference.start_ms,
                    end_ms=reference.end_ms,
                    chunk_id=chunk.id,
                )
            if start_sec is None or end_sec is None or end_sec <= start_sec:
                return None
            return MediaSegmentLocator(
                start_ms=start_sec * 1_000,
                end_ms=end_sec * 1_000,
                chunk_id=chunk.id,
            )
        if chunk.page_no is not None:
            raw_bbox = (chunk.metadata_ or {}).get("normalized_bbox")
            if isinstance(raw_bbox, (list, tuple)) and len(raw_bbox) == 4:
                try:
                    return PdfRegionLocator(
                        page_no=chunk.page_no,
                        bbox=tuple(float(value) for value in raw_bbox),  # type: ignore[arg-type]
                        chunk_id=chunk.id,
                    )
                except ValueError:
                    return None
        return TextSpanLocator(chunk_id=chunk.id, start_offset=start, end_offset=end)

    def _infer_watchlist_id(self, item: InvestmentItem) -> str | None:
        if not item.source_id:
            return None
        source = self.session.get(InvestmentSource, item.source_id)
        ids = [str(v) for v in (source.default_watchlist_ids or [])] if source else []
        return ids[0] if ids else None

    def _youtube_extra_context(self, item: InvestmentItem) -> str:
        if not item.document_id:
            return ""
        document = self.session.get(Document, item.document_id)
        if document is None or document.source_type != "youtube":
            return ""
        parts: list[str] = []
        if document.summary_json:
            parts.append(f"YouTube 总结:\n{_compact_json_text(document.summary_json)}")
        latest_version = self.session.scalar(
            select(DocumentVersion)
            .where(DocumentVersion.doc_id == document.id)
            .order_by(DocumentVersion.version_no.desc())
        )
        if latest_version is not None and latest_version.content_text:
            parts.append(f"YouTube 原字幕:\n{latest_version.content_text[:6000]}")
        if document.video_id:
            frames = list(
                self.session.scalars(
                    select(VideoFrameAnalysis)
                    .where(VideoFrameAnalysis.video_id == document.video_id)
                    .order_by(VideoFrameAnalysis.timestamp_sec)
                    .limit(20)
                )
            )
            if frames:
                lines = []
                for frame in frames:
                    frame_text = "\n".join(
                        value
                        for value in [
                            f"[{frame.timestamp_str}] {frame.frame_type}",
                            frame.ocr_text,
                            _compact_json_text(frame.structured_notes or {}),
                        ]
                        if value
                    )
                    if frame_text:
                        lines.append(frame_text)
                if lines:
                    parts.append("视觉资料 OCR:\n" + "\n\n".join(lines)[:6000])
        return "\n\n".join(parts)

class InvestmentFactJobHandler:
    """Extract facts for a single item or a bounded batch from one source."""

    def handle(
        self,
        job: TaskJob,
        session: Session,
        llm_client: StructuredOutputClient,
    ) -> dict[str, Any]:
        workspace_id = str((job.input or {}).get("workspace_id") or job.workspace_id)
        item_id = (job.input or {}).get("item_id")
        source_id = (job.input or {}).get("source_id")
        service = InvestmentFactExtractionService(session=session, llm_client=llm_client)
        matcher = InvestmentHypothesisMatcher(session)

        if item_id:
            result = service.extract_item(str(item_id))
            match_result = matcher.match_item_facts(str(item_id))
            InvestmentSignalService(session).refresh_signals(workspace_id)
            return {
                "workspace_id": workspace_id,
                "item_id": item_id,
                **result,
                **match_result,
            }

        conditions = [InvestmentItem.workspace_id == workspace_id]
        if source_id:
            conditions.append(InvestmentItem.source_id == str(source_id))
        items = list(
            session.scalars(
                select(InvestmentItem)
                .where(*conditions)
                .order_by(InvestmentItem.created_at)
                .limit(20)
            )
        )
        processed = 0
        facts_created = 0
        facts_reused = 0
        facts_skipped = 0
        failure_reasons: dict[str, int] = {}
        claims_created = 0
        for item in items:
            out = service.extract_item(item.id)
            match_result = matcher.match_item_facts(item.id)
            processed += out["items_processed"]
            facts_created += out["facts_created"]
            facts_reused += out.get("facts_reused", 0)
            facts_skipped += out.get("facts_skipped", 0)
            for reason, count in out.get("failure_reasons", {}).items():
                failure_reasons[reason] = failure_reasons.get(reason, 0) + count
            claims_created += match_result["claims_created"]
        InvestmentSignalService(session).refresh_signals(workspace_id)
        return {
            "workspace_id": workspace_id,
            "source_id": source_id,
            "items_processed": processed,
            "facts_created": facts_created,
            "facts_reused": facts_reused,
            "facts_skipped": facts_skipped,
            "failure_reasons": failure_reasons,
            "claims_created": claims_created,
        }


_HANDLER = InvestmentFactJobHandler()


class _FactSkip(Exception):
    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


def _fact_key(item_id: str, anchor_id: str, fact_text: str) -> str:
    normalized = _normalize_match_text(fact_text)
    return sha256(f"{item_id}|{anchor_id}|{normalized}".encode()).hexdigest()


def _investment_item_text(item: InvestmentItem) -> str:
    values = [item.title, item.summary, item.title_zh, item.summary_zh]
    return "\n".join(str(value) for value in values if value)


def _locator_from_anchor(anchor: EvidenceAnchor) -> EvidenceLocator:
    locator_type = anchor.locator.get("type")
    if locator_type == "text_span":
        return TextSpanLocator.model_validate(anchor.locator)
    if locator_type == "pdf_region":
        return PdfRegionLocator.model_validate(anchor.locator)
    if locator_type == "media_segment":
        return MediaSegmentLocator.model_validate(anchor.locator)
    if locator_type == "image_region":
        return ImageRegionLocator.model_validate(anchor.locator)
    return WebFragmentLocator.model_validate(anchor.locator)


def _timestamp_from_locator(locator: EvidenceLocator) -> int | None:
    if isinstance(locator, MediaSegmentLocator):
        return locator.start_ms // 1_000
    return None


def _failure_reason(error: Exception) -> str:
    if isinstance(error, AppError):
        if error.code == "evidence_anchor_mismatch":
            return "evidence_quote_mismatch"
        if error.code == "provenance_object_not_found":
            return "evidence_source_not_found"
    return "provenance_write_failed"


def _normalize_match_text(value: str | None) -> str:
    return " ".join(str(value or "").lower().split())


def _compact_json_text(value: object) -> str:
    if isinstance(value, dict):
        chunks: list[str] = []
        for key, item in value.items():
            if isinstance(item, list):
                chunks.append(f"{key}: " + "；".join(_compact_json_text(v) for v in item))
            elif isinstance(item, dict):
                chunks.append(f"{key}: {_compact_json_text(item)}")
            elif item is not None:
                chunks.append(f"{key}: {item}")
        return "\n".join(chunk for chunk in chunks if chunk.strip())
    return str(value)
