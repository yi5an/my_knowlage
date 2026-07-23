"""Persistent, evidence-grounded conversations for the global companion."""

from __future__ import annotations

from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.infrastructure.models import CompanionMessage, CompanionSession
from app.schemas.companion import (
    CompanionCitation,
    CompanionMessageResponse,
    CompanionReplyDraft,
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


def _message_response(message: CompanionMessage) -> CompanionMessageResponse:
    return CompanionMessageResponse(
        id=message.id,
        role=message.role,  # type: ignore[arg-type]
        content=message.content,
        citations=[CompanionCitation.model_validate(item) for item in message.citations or []],
        confidence=message.confidence,
    )


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"
