"""Evidence-backed fact extraction for investment items."""

from __future__ import annotations

import logging
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.infrastructure.models import (
    Document,
    DocumentChunk,
    DocumentVersion,
    InvestmentFact,
    InvestmentItem,
    InvestmentSource,
    TaskJob,
    VideoFrameAnalysis,
)
from app.services.investment.hypothesis_matcher import InvestmentHypothesisMatcher
from app.services.investment.signal_service import InvestmentSignalService
from app.services.structured_output import StructuredOutputClient

logger = logging.getLogger(__name__)

INVESTMENT_FACT_EXTRACTION_JOB_TYPE = "investment_fact_extract"


class InvestmentFactExtractionItem(BaseModel):
    fact_text: str = Field(min_length=1)
    fact_text_zh: str | None = None
    fact_type: str = Field(default="other")
    entities: list[str] = Field(default_factory=list)
    evidence_url: str | None = None
    evidence_excerpt: str = Field(min_length=1)
    evidence_timestamp: int | None = None
    confidence: float = Field(ge=0, le=1)


class InvestmentFactExtractionSchema(BaseModel):
    facts: list[InvestmentFactExtractionItem] = Field(default_factory=list, max_length=10)


SYSTEM_RULES = """你是投资研究事实抽取助手。规则：
1. 只抽取文本中明确出现的信息，不补充外部知识。
2. 观点、预测、传闻也可以抽取，但 fact_type 必须标明 opinion/prediction/rumor。
3. 每条事实必须带 evidence_excerpt 和 confidence。
4. 如果不能从文本找到证据，不要输出该事实。
5. 最多输出 10 条高价值事实，严格输出 JSON。"""


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


def _build_prompt(item: InvestmentItem, extra_context: str = "") -> str:
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
    return (
        f"{SYSTEM_RULES}\n\n"
        f"信息层级: {item.info_layer}\n"
        f"来源可信度: {item.source_credibility}\n"
        f"来源名称: {item.source_name or '未知'}\n"
        f"来源链接: {item.source_url or '无'}\n\n"
        f"文本:\n{text}\n\n"
        "请抽取事实点。"
    )


class InvestmentFactExtractionService:
    def __init__(self, session: Session, llm_client: StructuredOutputClient) -> None:
        self.session = session
        self.llm_client = llm_client

    def extract_item(self, item_id: str) -> dict[str, int]:
        item = self.session.get(InvestmentItem, item_id)
        if item is None:
            raise ValueError(f"investment item {item_id!r} not found")

        result = self.llm_client.generate(
            _build_prompt(item, self._youtube_extra_context(item)),
            InvestmentFactExtractionSchema,
        )
        watchlist_id = self._infer_watchlist_id(item)

        self.session.execute(
            delete(InvestmentFact).where(InvestmentFact.source_item_id == item.id)
        )
        created = 0
        for fact in result.facts[:10]:
            evidence_excerpt = fact.evidence_excerpt.strip()
            if not fact.fact_text.strip() or not evidence_excerpt:
                continue
            self.session.add(
                InvestmentFact(
                    id=_new_id("fact"),
                    workspace_id=item.workspace_id,
                    source_item_id=item.id,
                    watchlist_id=watchlist_id,
                    fact_text=fact.fact_text.strip(),
                    fact_text_zh=fact.fact_text_zh.strip() if fact.fact_text_zh else None,
                    fact_type=fact.fact_type.strip() or "other",
                    entities=[str(entity) for entity in fact.entities if str(entity).strip()],
                    evidence_url=fact.evidence_url or item.source_url,
                    evidence_excerpt=evidence_excerpt,
                    evidence_timestamp=fact.evidence_timestamp
                    if fact.evidence_timestamp is not None
                    else self._infer_evidence_timestamp(item, fact),
                    confidence=float(fact.confidence),
                    verification_status="pending",
                )
            )
            created += 1
        self.session.commit()
        logger.info("investment fact extraction: item %s -> %d facts", item.id, created)
        return {"items_processed": 1, "facts_created": created}

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

    def _infer_evidence_timestamp(
        self,
        item: InvestmentItem,
        fact: InvestmentFactExtractionItem,
    ) -> int | None:
        if not item.document_id:
            return None
        chunks = list(
            self.session.scalars(
                select(DocumentChunk)
                .where(DocumentChunk.doc_id == item.document_id)
                .order_by(DocumentChunk.chunk_index)
            )
        )
        candidates = [
            _normalize_match_text(fact.evidence_excerpt),
            _normalize_match_text(fact.fact_text),
        ]
        candidates = [candidate for candidate in candidates if len(candidate) >= 16]
        if not candidates:
            return None
        for chunk in chunks:
            content = _normalize_match_text(chunk.content)
            if any(candidate in content for candidate in candidates):
                return chunk.start_offset
        return None


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
        claims_created = 0
        for item in items:
            out = service.extract_item(item.id)
            match_result = matcher.match_item_facts(item.id)
            processed += out["items_processed"]
            facts_created += out["facts_created"]
            claims_created += match_result["claims_created"]
        InvestmentSignalService(session).refresh_signals(workspace_id)
        return {
            "workspace_id": workspace_id,
            "source_id": source_id,
            "items_processed": processed,
            "facts_created": facts_created,
            "claims_created": claims_created,
        }


_HANDLER = InvestmentFactJobHandler()


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
