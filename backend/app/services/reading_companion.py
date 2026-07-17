from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.infrastructure.models import (
    Document,
    DocumentChunk,
    DocumentVersion,
    ReadingAnalysis,
    ReadingCorroboration,
    ReadingInsight,
    TaskJob,
)
from app.schemas.reading_companion import (
    CorroborationVerdictSchema,
    ReadingAnalysisStatus,
    ReadingInsightDraft,
    ReadingInsightExtractionSchema,
    ReadingInsightUpdateRequest,
)
from app.services.reading_companion_prompts import (
    PROMPT_VERSION,
    build_corroboration_prompt,
    build_insight_prompt,
)
from app.services.reading_evidence import ReadingEvidenceAdapter
from app.services.structured_output import StructuredOutputClient

READING_ANALYSIS_JOB_TYPE = "reading_analysis"


class ReadingCompanionService:
    def __init__(
        self,
        session: Session,
        llm_client: StructuredOutputClient,
        evidence_adapter: ReadingEvidenceAdapter,
    ) -> None:
        self.session = session
        self.llm_client = llm_client
        self.evidence_adapter = evidence_adapter

    @staticmethod
    def validate_anchor(chunk_content: str, draft: ReadingInsightDraft) -> tuple[int, int] | None:
        expected = draft.evidence_text
        if chunk_content[draft.start_offset : draft.end_offset] == expected:
            return draft.start_offset, draft.end_offset
        first = chunk_content.find(expected)
        if first < 0 or chunk_content.find(expected, first + 1) >= 0:
            return None
        return first, first + len(expected)

    def create_or_reuse_analysis(self, document_id: str) -> tuple[ReadingAnalysis, TaskJob]:
        document, version = self._document_and_version(document_id)
        analysis = self.session.scalar(
            select(ReadingAnalysis).where(
                ReadingAnalysis.document_id == document.id,
                ReadingAnalysis.version_id == version.id,
            )
        )
        if analysis is not None and analysis.task_job_id:
            job = self.session.get(TaskJob, analysis.task_job_id)
            if job is not None:
                return analysis, job
        if analysis is None:
            analysis = ReadingAnalysis(
                id=_new_id("reading"),
                workspace_id=document.workspace_id,
                document_id=document.id,
                version_id=version.id,
                status=ReadingAnalysisStatus.pending.value,
                prompt_version=PROMPT_VERSION,
            )
            self.session.add(analysis)
            self.session.flush()
        job = TaskJob(
            id=_new_id("task"),
            workspace_id=document.workspace_id,
            job_type=READING_ANALYSIS_JOB_TYPE,
            target_type="reading_analysis",
            target_id=analysis.id,
            input={
                "analysis_id": analysis.id,
                "document_id": document.id,
                "version_id": version.id,
            },
        )
        analysis.task_job_id = job.id
        analysis.status = ReadingAnalysisStatus.pending.value
        self.session.add(job)
        self.session.commit()
        return analysis, job

    def update_insight(
        self, insight_id: str, request: ReadingInsightUpdateRequest
    ) -> ReadingInsight:
        insight = self.session.get(ReadingInsight, insight_id)
        if insight is None:
            raise ValueError(f"reading insight {insight_id!r} not found")
        insight.status = request.status
        if request.note is not None:
            insight.user_note = request.note
        self.session.commit()
        return insight

    def run_analysis(self, analysis_id: str) -> list[ReadingInsight]:
        analysis = self.session.get(ReadingAnalysis, analysis_id)
        if analysis is None:
            raise ValueError(f"reading analysis {analysis_id!r} not found")
        document = self.session.get(Document, analysis.document_id)
        if document is None:
            raise ValueError(f"document {analysis.document_id!r} not found")
        analysis.status = ReadingAnalysisStatus.running.value
        self.session.flush()
        persisted: list[ReadingInsight] = []
        chunks = list(
            self.session.scalars(
                select(DocumentChunk)
                .where(DocumentChunk.version_id == analysis.version_id)
                .order_by(DocumentChunk.chunk_index)
            )
        )
        for chunk in chunks:
            result = self.llm_client.generate(
                build_insight_prompt(
                    title=document.title,
                    chunk_id=chunk.id,
                    content=chunk.content,
                ),
                ReadingInsightExtractionSchema,
            )
            for draft in result.insights:
                if draft.chunk_id != chunk.id:
                    continue
                anchor = self.validate_anchor(chunk.content, draft)
                if anchor is None:
                    continue
                start_offset, end_offset = anchor
                insight = ReadingInsight(
                    id=_new_id("insight"),
                    analysis_id=analysis.id,
                    kind=draft.kind.value,
                    headline=draft.headline,
                    explanation=draft.explanation,
                    why_it_matters=draft.why_it_matters,
                    chunk_id=chunk.id,
                    start_offset=start_offset,
                    end_offset=end_offset,
                    evidence_text=draft.evidence_text,
                    confidence=draft.confidence,
                    priority=draft.priority,
                    evidence_state="insufficient",
                    theme_ids=draft.theme_ids,
                    macro_event_ids=draft.macro_event_ids,
                    entity_ids=draft.entity_ids,
                )
                self.session.add(insight)
                self.session.flush()
                self._add_corroborations(analysis, insight, draft)
                persisted.append(insight)
        self.session.add_all(persisted)
        analysis.status = ReadingAnalysisStatus.completed.value
        analysis.completed_at = datetime.now(UTC)
        self.session.commit()
        return persisted

    def _add_corroborations(
        self,
        analysis: ReadingAnalysis,
        insight: ReadingInsight,
        draft: ReadingInsightDraft,
    ) -> None:
        candidates = self.evidence_adapter.search(
            workspace_id=analysis.workspace_id,
            query=f"{draft.headline} {draft.evidence_text}",
            excluded_chunk_ids={draft.chunk_id},
        )
        if not candidates:
            return
        verdicts = self.llm_client.generate(
            build_corroboration_prompt(
                headline=draft.headline,
                explanation=draft.explanation,
                candidates=candidates,
            ),
            CorroborationVerdictSchema,
        )
        by_id = {candidate.source_id: candidate for candidate in candidates}
        stances: set[str] = set()
        for verdict in verdicts.corroborations:
            candidate = by_id.get(verdict.source_id)
            if candidate is None:
                continue
            stances.add(verdict.stance.value)
            self.session.add(
                ReadingCorroboration(
                    id=_new_id("corroboration"),
                    insight_id=insight.id,
                    source_kind=candidate.source_kind,
                    source_id=candidate.source_id,
                    document_id=candidate.document_id,
                    chunk_id=candidate.chunk_id,
                    stance=verdict.stance.value,
                    excerpt=verdict.excerpt,
                    source_title=candidate.title,
                    source_published_at=candidate.published_at,
                    confidence=verdict.confidence,
                    retrieval_score=candidate.retrieval_score,
                )
            )
        if "contradicts" in stances:
            insight.evidence_state = "conflicted"
        elif stances:
            insight.evidence_state = "corroborated"

    def _document_and_version(self, document_id: str) -> tuple[Document, DocumentVersion]:
        document = self.session.get(Document, document_id)
        if document is None:
            raise ValueError(f"document {document_id!r} not found")
        version_id = str((document.metadata_ or {}).get("current_version_id") or "")
        version = self.session.get(DocumentVersion, version_id) if version_id else None
        if version is None:
            version = self.session.scalar(
                select(DocumentVersion)
                .where(DocumentVersion.doc_id == document.id)
                .order_by(DocumentVersion.version_no.desc())
            )
        if version is None:
            raise ValueError(f"document {document_id!r} has no version")
        return document, version


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"
