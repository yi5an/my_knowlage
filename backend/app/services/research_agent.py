from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.infrastructure.models import (
    Document,
    DocumentChunk,
    DocumentVersion,
    ResearchSource,
    ResearchTask,
    TaskJob,
)
from app.schemas.research import (
    CrossCheckedClaims,
    ExtractedClaims,
    ResearchClaim,
    ResearchPlan,
    ResearchReport,
    ResearchSourceItem,
    ResearchTaskCreateRequest,
)
from app.services.research_prompts import (
    build_cross_check_prompt,
    build_extract_claims_prompt,
    build_plan_prompt,
    build_report_prompt,
)
from app.services.structured_output import StructuredOutputClient
from app.services.web_search import WebSearchClient

logger = logging.getLogger(__name__)


class ResearchWorkflowError(Exception):
    """Raised when a research workflow node fails irrecoverably."""


class LocalKnowledgeSearchClient(Protocol):
    def search(self, query: str, workspace_id: str, limit: int = 5) -> list[ResearchSourceItem]:
        ...


class DatabaseLocalKnowledgeSearchClient:
    def __init__(self, session: Session) -> None:
        self.session = session

    def search(self, query: str, workspace_id: str, limit: int = 5) -> list[ResearchSourceItem]:
        terms = [term for term in query.lower().split() if term]
        statement = (
            select(DocumentChunk, Document)
            .join(Document, Document.id == DocumentChunk.doc_id)
            .where(Document.workspace_id == workspace_id)
            .limit(100)
        )
        scored: list[tuple[int, DocumentChunk, Document]] = []
        for chunk, document in self.session.execute(statement).all():
            content = f"{document.title} {chunk.heading or ''} {chunk.content}".lower()
            score = sum(content.count(term) for term in terms)
            if score > 0:
                scored.append((score, chunk, document))
        scored.sort(key=lambda item: item[0], reverse=True)
        return [
            ResearchSourceItem(
                source_type="local",
                title=document.title,
                doc_id=document.id,
                snippet=chunk.content,
                credibility_score=0.85,
            )
            for _, chunk, document in scored[:limit]
        ]


@dataclass(frozen=True)
class WorkflowState:
    task: ResearchTask
    plan: ResearchPlan | None
    local_sources: list[ResearchSourceItem]
    web_sources: list[ResearchSourceItem]
    all_sources: list[ResearchSourceItem]
    claims: list[ResearchClaim]
    report: ResearchReport | None = None


class ResearchAgentService:
    WORKFLOW_NODES = [
        "PlanResearchNode",
        "SearchLocalKnowledgeNode",
        "SearchWebNode",
        "ReadSourcesNode",
        "ExtractClaimsNode",
        "CrossCheckNode",
        "GenerateReportNode",
        "ImportToKnowledgeBaseNode",
    ]

    def __init__(
        self,
        session: Session,
        llm_client: StructuredOutputClient,
        local_search_client: LocalKnowledgeSearchClient | None = None,
        web_search_client: WebSearchClient | None = None,
        session_factory: Any = None,
    ) -> None:
        self.session = session
        self.llm_client = llm_client
        self.local_search_client = (
            local_search_client or DatabaseLocalKnowledgeSearchClient(session)
        )
        # Web search defaults to None: the workflow treats a missing client as
        # a hard config error (Tavily key not set) rather than silently mock.
        self.web_search_client = web_search_client
        # Optional session factory for the background workflow thread. In
        # production this is left None and the thread uses SessionLocal; tests
        # pass their own factory so the background session hits the same
        # in-memory DB as the test fixture.
        self.session_factory = session_factory

    def create_task(self, request: ResearchTaskCreateRequest) -> ResearchTask:
        """Create a research task and start the workflow in the background.

        Returns immediately with status="running" so the HTTP request is not
        blocked for the 2-3 minutes the LLM workflow takes. The workflow runs
        in a daemon thread with its own DB session; the client polls
        ``GET /research/tasks/{id}`` for progress.
        """
        task = ResearchTask(
            id=f"research_{uuid4().hex}",
            workspace_id=request.workspace_id,
            title=request.title,
            question=request.question,
            status="running",
            plan={},
            metadata_={"workflow_steps": self._initial_steps()},
        )
        self.session.add(task)
        self.session.commit()
        self.session.refresh(task)
        self._run_workflow_async(task.id)
        return task

    def _run_workflow_async(self, task_id: str) -> None:
        """Run the workflow in a background thread with a fresh DB session.

        SQLAlchemy sessions are not thread-safe, so the background run must
        build its own session + service instance rather than reuse the
        request-scoped ones.
        """
        import threading

        llm_client = self.llm_client
        web_client = self.web_search_client
        session_factory = self.session_factory
        local_client = self.local_search_client

        def _run() -> None:
            from app.infrastructure.database import SessionLocal

            factory = session_factory if session_factory is not None else SessionLocal
            session = factory()
            try:
                # Reuse the LLM and web clients (stateless w.r.t. the DB). The
                # local-search client is reused only if it's NOT bound to the
                # request session (e.g. a test mock); the DB-backed default is
                # rebuilt on the new session so it stays thread-safe.
                reusable_local = (
                    local_client
                    if not isinstance(local_client, DatabaseLocalKnowledgeSearchClient)
                    else None
                )
                service = ResearchAgentService(
                    session=session,
                    llm_client=llm_client,
                    local_search_client=reusable_local,
                    web_search_client=web_client,
                    session_factory=session_factory,
                )
                service.run_workflow(task_id)
            except Exception:  # noqa: BLE001
                logger.exception("background research workflow failed: %s", task_id)
            finally:
                session.close()

        thread = threading.Thread(target=_run, daemon=True, name=f"research-{task_id}")
        thread.start()

    def get_task(self, task_id: str) -> ResearchTask | None:
        return self.session.get(ResearchTask, task_id)

    def progress(self, task: ResearchTask) -> tuple[int, list[dict[str, Any]]]:
        steps = self._steps(task)
        if not steps:
            return 0, []
        completed = sum(1 for step in steps if step.get("status") == "completed")
        return int((completed / len(steps)) * 100), steps

    def run_workflow(self, task_id: str) -> ResearchTask:
        task = self.session.get(ResearchTask, task_id)
        if task is None:
            msg = f"Research task not found: {task_id}"
            raise ValueError(msg)
        # The last node (ImportToKnowledgeBaseNode) is completed by import_report,
        # not by the workflow, so it stays pending here. That keeps the 7/8 = 87%
        # progress contract intact.
        state = WorkflowState(
            task=task,
            plan=None,
            local_sources=[],
            web_sources=[],
            all_sources=[],
            claims=[],
        )
        try:
            state = self._plan_research(state)
            state = self._search_local_knowledge(state)
            state = self._search_web(state)
            state = self._read_sources(state)
            state = self._extract_claims(state)
            state = self._cross_check(state)
            state = self._generate_report(state)
        except Exception as exc:  # noqa: BLE001
            # Strict failure mode: any node failure fails the whole workflow.
            # Persist the failure so the client can read status + reason even
            # though run_workflow re-raises.
            self._fail_task(task, exc)
            raise
        task.status = "completed"
        self.session.commit()
        return task

    def import_report(self, task_id: str) -> tuple[Document, list[TaskJob]]:
        task = self.session.get(ResearchTask, task_id)
        if task is None:
            msg = f"Research task not found: {task_id}"
            raise ValueError(msg)
        report = ResearchReport.model_validate((task.metadata_ or {}).get("report", {}))
        content_md = _report_to_markdown(report)
        document = Document(
            id=f"doc_{uuid4().hex}",
            workspace_id=task.workspace_id,
            title=task.title,
            source_type="research_report",
            parse_status="completed",
            index_status="pending",
            entity_status="pending",
            relation_status="pending",
            metadata_={"research_task_id": task.id},
        )
        version = DocumentVersion(
            id=f"version_{uuid4().hex}",
            doc_id=document.id,
            version_no=1,
            title=document.title,
            content_md=content_md,
            content_text=content_md,
        )
        chunk = DocumentChunk(
            id=f"chunk_{uuid4().hex}",
            doc_id=document.id,
            version_id=version.id,
            chunk_index=0,
            heading="Research report",
            content=content_md,
        )
        jobs = [
            TaskJob(
                id=f"task_{uuid4().hex}",
                workspace_id=task.workspace_id,
                job_type="entity_extraction",
                target_type="document",
                target_id=document.id,
                status="pending",
                input={"document_id": document.id},
            ),
            TaskJob(
                id=f"task_{uuid4().hex}",
                workspace_id=task.workspace_id,
                job_type="relation_extraction",
                target_type="document",
                target_id=document.id,
                status="pending",
                input={"document_id": document.id},
            ),
        ]
        task.report_doc_id = document.id
        task.status = "imported"
        self._complete_step(task, "ImportToKnowledgeBaseNode", {"document_id": document.id})
        self.session.add_all([document, version, chunk, *jobs])
        self.session.commit()
        self.session.refresh(document)
        return document, jobs

    # --- LLM-driven nodes --------------------------------------------------

    def _plan_research(self, state: WorkflowState) -> WorkflowState:
        plan = self.llm_client.generate(
            build_plan_prompt(state.task.question), ResearchPlan
        )
        stored = {
            "question": state.task.question,
            "queries": plan.queries,
            "rationale": plan.rationale,
        }
        state.task.plan = stored
        self._complete_step(state.task, "PlanResearchNode", stored)
        return _with(state, plan=plan)

    def _search_local_knowledge(self, state: WorkflowState) -> WorkflowState:
        queries = _retrieval_queries(state)
        merged: list[ResearchSourceItem] = []
        seen: set[tuple[str, str]] = set()
        for q in queries:
            for src in self.local_search_client.search(
                q, state.task.workspace_id, limit=5
            ):
                key = (src.doc_id or src.url or src.title, src.snippet)
                if key in seen:
                    continue
                seen.add(key)
                merged.append(src)
        self._store_sources(state.task.id, merged)
        self._complete_step(
            state.task,
            "SearchLocalKnowledgeNode",
            {"source_count": len(merged)},
        )
        return _with(state, local_sources=merged)

    def _search_web(self, state: WorkflowState) -> WorkflowState:
        if self.web_search_client is None:
            raise ResearchWorkflowError(
                "web search is not configured (TAVILY_API_KEY missing)"
            )
        queries = _retrieval_queries(state)
        merged: list[ResearchSourceItem] = []
        seen: set[tuple[str, str]] = set()
        for q in queries:
            for src in self.web_search_client.search(q, limit=5):
                key = (src.url or src.title, src.snippet)
                if key in seen:
                    continue
                seen.add(key)
                merged.append(src)
        self._store_sources(state.task.id, merged)
        self._complete_step(state.task, "SearchWebNode", {"source_count": len(merged)})
        return _with(state, web_sources=merged)

    def _read_sources(self, state: WorkflowState) -> WorkflowState:
        all_sources = [*state.local_sources, *state.web_sources]
        self._complete_step(state.task, "ReadSourcesNode", {"source_count": len(all_sources)})
        return _with(state, all_sources=all_sources)

    def _extract_claims(self, state: WorkflowState) -> WorkflowState:
        try:
            extracted = self.llm_client.generate(
                build_extract_claims_prompt(state.task.question, state.all_sources),
                ExtractedClaims,
            )
            claims = extracted.claims
        except Exception as exc:  # noqa: BLE001
            # LLM structured-output failures are common on complex Chinese
            # payloads. Fall back to using source snippets directly as claims
            # so the workflow can still produce a report instead of aborting.
            logger.warning("ExtractClaimsNode LLM failed, using fallback: %s", exc)
            claims = [
                ResearchClaim(
                    text=src.snippet,
                    evidence=[src.title],
                    confidence=src.credibility_score,
                )
                for src in state.all_sources
                if src.snippet
            ][:8]
        self._complete_step(state.task, "ExtractClaimsNode", {"claim_count": len(claims)})
        return _with(state, claims=claims)

    def _cross_check(self, state: WorkflowState) -> WorkflowState:
        try:
            checked = self.llm_client.generate(
                build_cross_check_prompt(state.task.question, state.claims),
                CrossCheckedClaims,
            )
            claims = checked.claims
        except Exception as exc:  # noqa: BLE001
            logger.warning("CrossCheckNode LLM failed, using fallback: %s", exc)
            # Keep claims as-is (no cross-validation) rather than abort.
            claims = state.claims
        self._complete_step(
            state.task, "CrossCheckNode", {"claim_count": len(claims)}
        )
        return _with(state, claims=claims)

    def _generate_report(self, state: WorkflowState) -> WorkflowState:
        try:
            report = self.llm_client.generate(
                build_report_prompt(
                    state.task.question,
                    state.task.title,
                    state.all_sources,
                    state.claims,
                ),
                ResearchReport,
            )
        except Exception as exc:  # noqa: BLE001
            # Report generation is the last step; failing here wastes the whole
            # run. Fall back to a structured report assembled from claims.
            logger.warning("GenerateReportNode LLM failed, using fallback: %s", exc)
            report = _fallback_report(state)
        metadata = dict(state.task.metadata_ or {})
        metadata["report"] = report.model_dump()
        state.task.metadata_ = metadata
        self._complete_step(state.task, "GenerateReportNode", report.model_dump())
        self.session.commit()
        return _with(state, report=report)

    # --- persistence helpers ----------------------------------------------

    def _store_sources(self, task_id: str, sources: list[ResearchSourceItem]) -> None:
        for source in sources:
            self.session.add(
                ResearchSource(
                    id=f"rsrc_{uuid4().hex}",
                    research_task_id=task_id,
                    source_type=source.source_type,
                    title=source.title,
                    url=source.url,
                    doc_id=source.doc_id,
                    snippet=source.snippet,
                    credibility_score=source.credibility_score,
                    used_in_report=True,
                )
            )
        self.session.flush()

    def _fail_task(self, task: ResearchTask, exc: Exception) -> None:
        node = _current_node_name(self._steps(task))
        metadata = dict(task.metadata_ or {})
        metadata["error"] = {
            "node": node,
            "type": type(exc).__name__,
            "message": str(exc),
        }
        task.metadata_ = metadata
        task.status = "failed"
        self.session.commit()
        logger.warning("research workflow failed at %s: %s", node, exc)

    def _initial_steps(self) -> list[dict[str, Any]]:
        return [
            {
                "name": node,
                "status": "pending",
                "input": {},
                "output": {},
                "updated_at": None,
            }
            for node in self.WORKFLOW_NODES
        ]

    def _steps(self, task: ResearchTask) -> list[dict[str, Any]]:
        steps = (task.metadata_ or {}).get("workflow_steps", [])
        return steps if isinstance(steps, list) else []

    def _complete_step(self, task: ResearchTask, node_name: str, output: dict[str, Any]) -> None:
        metadata = dict(task.metadata_ or {})
        steps = metadata.get("workflow_steps", self._initial_steps())
        if not isinstance(steps, list):
            steps = self._initial_steps()
        for step in steps:
            if isinstance(step, dict) and step.get("name") == node_name:
                step["status"] = "completed"
                step["output"] = output
                step["updated_at"] = datetime.now(UTC).isoformat()
        metadata["workflow_steps"] = steps
        task.metadata_ = metadata
        self.session.flush()


def _retrieval_queries(state: WorkflowState) -> list[str]:
    """Queries to feed local + web search: plan sub-queries, falling back to
    the raw question so a single-query plan still searches at least once."""
    if state.plan and state.plan.queries:
        return state.plan.queries
    return [state.task.question]


def _current_node_name(steps: list[dict[str, Any]]) -> str:
    """Name of the first pending workflow step (the one that failed)."""
    for step in steps:
        if isinstance(step, dict) and step.get("status") != "completed":
            return str(step.get("name", "UnknownNode"))
    return "UnknownNode"


def _with(
    state: WorkflowState,
    *,
    plan: ResearchPlan | None = None,
    local_sources: list[ResearchSourceItem] | None = None,
    web_sources: list[ResearchSourceItem] | None = None,
    all_sources: list[ResearchSourceItem] | None = None,
    claims: list[ResearchClaim] | None = None,
    report: ResearchReport | None = None,
) -> WorkflowState:
    """Return a copy of an immutable WorkflowState with selected fields replaced.

    Takes only keyword args for the fields to override (None means "keep the
    current value"), so callers read as ``_with(state, plan=...)`` while mypy
    can still type-check each field instead of losing precision through a
    ``**kwargs`` dict spread.
    """
    return WorkflowState(
        task=state.task,
        plan=plan if plan is not None else state.plan,
        local_sources=local_sources if local_sources is not None else state.local_sources,
        web_sources=web_sources if web_sources is not None else state.web_sources,
        all_sources=all_sources if all_sources is not None else state.all_sources,
        claims=claims if claims is not None else state.claims,
        report=report if report is not None else state.report,
    )


def _fallback_report(state: WorkflowState) -> ResearchReport:
    """Assemble a minimal report from claims/sources when the LLM fails.

    Used only as a last resort so a research task still yields a report
    instead of ending in failure due to one bad LLM call.
    """
    claims = state.claims or []
    findings = [c.text for c in claims[:6]] or ["暂无足够证据形成结论。"]
    evidence = [e for c in claims for e in c.evidence] or [
        s.title for s in state.all_sources
    ]
    src_count = len(state.all_sources)
    return ResearchReport(
        summary=(
            f"围绕「{state.task.question}」整理了基于 {src_count} 个来源的研究结论"
            "(LLM 报告生成失败,以下为来源摘要)。"
        ),
        background=f"研究任务:{state.task.title}。",
        key_findings=findings,
        evidence=evidence,
        comparison_table=[
            {
                "source": s.title,
                "type": s.source_type,
                "credibility": f"{s.credibility_score:.2f}",
            }
            for s in state.all_sources
        ],
        risks_and_uncertainties=["LLM 报告生成异常,结论为来源片段拼接,需人工复核。"],
        next_steps=["重新运行研究,或人工审阅来源后撰写报告。"],
    )


def _report_to_markdown(report: ResearchReport) -> str:
    table_rows = "\n".join(
        f"| {row.get('source', '')} | {row.get('type', '')} | {row.get('credibility', '')} |"
        for row in report.comparison_table
    )
    return "\n\n".join(
        [
            f"# {report.summary}",
            "## 背景\n" + report.background,
            "## 关键发现\n" + "\n".join(f"- {item}" for item in report.key_findings),
            "## 证据\n" + "\n".join(f"- {item}" for item in report.evidence),
            "## 对比表\n| 来源 | 类型 | 可信度 |\n| --- | --- | --- |\n" + table_rows,
            "## 风险与不确定性\n"
            + "\n".join(f"- {item}" for item in report.risks_and_uncertainties),
            "## 下一步建议\n" + "\n".join(f"- {item}" for item in report.next_steps),
        ]
    )
