"""Persistent, evidence-grounded conversations for the global companion."""

from __future__ import annotations

from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.infrastructure.models import CompanionInsight, CompanionMessage, CompanionSession, TaskJob
from app.schemas.companion import (
    CompanionCitation,
    CompanionInsightExtractionSchema,
    CompanionInsightResponse,
    CompanionMessageResponse,
    CompanionReplyDraft,
    CompanionSessionDetailResponse,
    CompanionSessionResponse,
    CompanionSubjectType,
)
from app.services.companion.context import CompanionContext, CompanionContextService
from app.services.structured_output import StructuredOutputClient


class CompanionService:
    def __init__(self, session: Session, llm_client: StructuredOutputClient) -> None:
        self.session = session
        self.llm_client = llm_client
        self.context_service = CompanionContextService(session)

    def create_or_reuse_session(
        self,
        workspace_id: str,
        subject_type: CompanionSubjectType,
        subject_id: str,
    ) -> CompanionSession:
        context = self.context_service.load(workspace_id, subject_type, subject_id)
        companion_session = self.session.scalar(
            select(CompanionSession).where(
                CompanionSession.workspace_id == workspace_id,
                CompanionSession.subject_type == subject_type,
                CompanionSession.subject_id == subject_id,
            )
        )
        if companion_session is not None:
            return companion_session
        companion_session = CompanionSession(
            id=_new_id("companion"),
            workspace_id=workspace_id,
            subject_type=subject_type,
            subject_id=subject_id,
            title=context.title,
        )
        self.session.add(companion_session)
        self.session.commit()
        return companion_session

    def submit_message(self, session_id: str, content: str) -> CompanionMessageResponse:
        companion_session = self._session(session_id)
        context = self.context_service.load(
            companion_session.workspace_id,
            companion_session.subject_type,  # type: ignore[arg-type]
            companion_session.subject_id,
        )
        context = self.context_service.with_related_evidence(
            context,
            companion_session.workspace_id,
            content,
        )
        self.session.add(
            CompanionMessage(
                id=_new_id("companion_message"),
                session_id=companion_session.id,
                role="user",
                content=content,
                citations=[],
            )
        )
        draft = self.llm_client.generate(
            _reply_prompt(context, content),
            CompanionReplyDraft,
        )
        citations = _safe_citations(context, draft.cited_source_ids)
        assistant = CompanionMessage(
            id=_new_id("companion_message"),
            session_id=companion_session.id,
            role="assistant",
            content=draft.content.strip() or _evidence_only_reply(context),
            citations=[citation.model_dump() for citation in citations],
            confidence=draft.confidence if draft.content.strip() else 0.5,
        )
        self.session.add(assistant)
        self.session.commit()
        return _message_response(assistant)

    def get_session(self, session_id: str) -> CompanionSessionDetailResponse:
        companion_session = self._session(session_id)
        messages = list(
            self.session.scalars(
                select(CompanionMessage)
                .where(CompanionMessage.session_id == companion_session.id)
                .order_by(CompanionMessage.created_at)
            )
        )
        insights = list(
            self.session.scalars(
                select(CompanionInsight)
                .where(
                    CompanionInsight.session_id == companion_session.id,
                    CompanionInsight.status == "active",
                )
                .order_by(CompanionInsight.created_at.desc())
            )
        )
        return CompanionSessionDetailResponse(
            **_session_response(companion_session).model_dump(),
            messages=[_message_response(message) for message in messages],
            insights=[_insight_response(insight) for insight in insights],
        )

    def create_insight_job(self, session_id: str) -> TaskJob:
        companion_session = self._session(session_id)
        active_job = self.session.scalar(
            select(TaskJob).where(
                TaskJob.workspace_id == companion_session.workspace_id,
                TaskJob.job_type == "companion_insights",
                TaskJob.target_type == "companion_session",
                TaskJob.target_id == companion_session.id,
                TaskJob.status.in_(("pending", "running")),
            )
        )
        if active_job is not None:
            return active_job
        job = TaskJob(
            id=_new_id("task"),
            workspace_id=companion_session.workspace_id,
            job_type="companion_insights",
            target_type="companion_session",
            target_id=companion_session.id,
            input={"companion_session_id": companion_session.id},
        )
        self.session.add(job)
        self.session.commit()
        return job

    def run_insight_job(self, session_id: str, task_job_id: str) -> list[CompanionInsight]:
        companion_session = self._session(session_id)
        context = self.context_service.load(
            companion_session.workspace_id,
            companion_session.subject_type,  # type: ignore[arg-type]
            companion_session.subject_id,
        )
        context = self.context_service.with_related_evidence(
            context,
            companion_session.workspace_id,
            "投资重点、待验证问题、风险与机会",
        )
        result = self.llm_client.generate(
            _insight_prompt(context),
            CompanionInsightExtractionSchema,
        )
        persisted: list[CompanionInsight] = []
        for draft in result.insights:
            insight = CompanionInsight(
                id=_new_id("companion_insight"),
                session_id=companion_session.id,
                task_job_id=task_job_id,
                kind=draft.kind,
                headline=draft.headline,
                content=draft.content,
                citations=[
                    citation.model_dump()
                    for citation in _safe_citations(context, draft.cited_source_ids)
                ],
                confidence=draft.confidence,
            )
            self.session.add(insight)
            persisted.append(insight)
        self.session.commit()
        return persisted

    def _session(self, session_id: str) -> CompanionSession:
        companion_session = self.session.get(CompanionSession, session_id)
        if companion_session is None:
            raise ValueError(f"companion session {session_id!r} not found")
        return companion_session


def _safe_citations(context: CompanionContext, source_ids: list[str]) -> list[CompanionCitation]:
    citations_by_id = {citation.source_id: citation for citation in context.citations}
    selected = [
        citations_by_id[source_id]
        for source_id in source_ids
        if source_id in citations_by_id
    ]
    return selected or context.citations[:4]


def _evidence_only_reply(context: CompanionContext) -> str:
    if not context.citations:
        return "当前内容尚未提供可引用的站内证据，建议补充资料后再判断。"
    return f"当前判断应先以《{context.title}》中的已标注证据为准；我已附上可追溯的原始片段。"


def _reply_prompt(context: CompanionContext, question: str) -> str:
    evidence = "\n".join(
        f"- [{citation.source_id}] {citation.source_title}: {citation.excerpt}"
        for citation in context.citations
    )
    return (
        "你是投资情报分析助手。只能根据给定站内证据回答，不可编造事实。"
        "回答要指出不确定性，并且 cited_source_ids 只能选择证据列表中的 ID。\n\n"
        f"当前对象：{context.title}\n问题：{question}\n证据：\n{evidence}"
    )


def _insight_prompt(context: CompanionContext) -> str:
    evidence = "\n".join(
        f"- [{citation.source_id}] {citation.source_title}: {citation.excerpt}"
        for citation in context.citations
    )
    return (
        "你是投资情报分析助手。仅基于给定站内证据，输出最多四条主动陪读提示，"
        "覆盖重点、待验证问题、风险、机会中有证据支持的部分。"
        "每条必须说明不确定性，并且 cited_source_ids 只能选择证据列表中的 ID。\n\n"
        f"当前对象：{context.title}\n证据：\n{evidence}"
    )


def _message_response(message: CompanionMessage) -> CompanionMessageResponse:
    return CompanionMessageResponse(
        id=message.id,
        role=message.role,  # type: ignore[arg-type]
        content=message.content,
        citations=[CompanionCitation.model_validate(item) for item in message.citations or []],
        confidence=message.confidence,
    )


def _session_response(session: CompanionSession) -> CompanionSessionResponse:
    return CompanionSessionResponse(
        id=session.id,
        workspace_id=session.workspace_id,
        subject_type=session.subject_type,  # type: ignore[arg-type]
        subject_id=session.subject_id,
        title=session.title,
        status=session.status,
    )


def _insight_response(insight: CompanionInsight) -> CompanionInsightResponse:
    return CompanionInsightResponse(
        id=insight.id,
        kind=insight.kind,  # type: ignore[arg-type]
        headline=insight.headline,
        content=insight.content,
        citations=[CompanionCitation.model_validate(item) for item in insight.citations or []],
        confidence=insight.confidence,
        status=insight.status,
    )


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"
