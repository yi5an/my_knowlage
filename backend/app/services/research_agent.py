from __future__ import annotations

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
    ResearchClaim,
    ResearchReport,
    ResearchSourceItem,
    ResearchTaskCreateRequest,
)
from app.services.web_search import MockWebSearchClient, WebSearchClient


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
        local_search_client: LocalKnowledgeSearchClient | None = None,
        web_search_client: WebSearchClient | None = None,
    ) -> None:
        self.session = session
        self.local_search_client = (
            local_search_client or DatabaseLocalKnowledgeSearchClient(session)
        )
        self.web_search_client = web_search_client or MockWebSearchClient()

    def create_task(self, request: ResearchTaskCreateRequest) -> ResearchTask:
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
        self.run_workflow(task.id)
        completed = self.get_task(task.id)
        if completed is None:
            msg = "Research task disappeared after creation."
            raise RuntimeError(msg)
        return completed

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
        state = WorkflowState(
            task=task,
            local_sources=[],
            web_sources=[],
            all_sources=[],
            claims=[],
        )
        state = self._plan_research(state)
        state = self._search_local_knowledge(state)
        state = self._search_web(state)
        state = self._read_sources(state)
        state = self._extract_claims(state)
        state = self._cross_check(state)
        state = self._generate_report(state)
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

    def _plan_research(self, state: WorkflowState) -> WorkflowState:
        plan = {
            "question": state.task.question,
            "queries": [state.task.question],
            "required_sections": [
                "摘要",
                "背景",
                "关键发现",
                "证据",
                "对比表",
                "风险与不确定性",
                "下一步建议",
            ],
        }
        state.task.plan = plan
        self._complete_step(state.task, "PlanResearchNode", plan)
        return state

    def _search_local_knowledge(self, state: WorkflowState) -> WorkflowState:
        sources = self.local_search_client.search(
            state.task.question,
            state.task.workspace_id,
            limit=5,
        )
        self._store_sources(state.task.id, sources)
        self._complete_step(
            state.task,
            "SearchLocalKnowledgeNode",
            {"source_count": len(sources)},
        )
        return WorkflowState(
            task=state.task,
            local_sources=sources,
            web_sources=state.web_sources,
            all_sources=state.all_sources,
            claims=state.claims,
            report=state.report,
        )

    def _search_web(self, state: WorkflowState) -> WorkflowState:
        sources = self.web_search_client.search(state.task.question, limit=5)
        self._store_sources(state.task.id, sources)
        self._complete_step(state.task, "SearchWebNode", {"source_count": len(sources)})
        return WorkflowState(
            task=state.task,
            local_sources=state.local_sources,
            web_sources=sources,
            all_sources=state.all_sources,
            claims=state.claims,
            report=state.report,
        )

    def _read_sources(self, state: WorkflowState) -> WorkflowState:
        all_sources = [*state.local_sources, *state.web_sources]
        self._complete_step(state.task, "ReadSourcesNode", {"source_count": len(all_sources)})
        return WorkflowState(
            task=state.task,
            local_sources=state.local_sources,
            web_sources=state.web_sources,
            all_sources=all_sources,
            claims=state.claims,
            report=state.report,
        )

    def _extract_claims(self, state: WorkflowState) -> WorkflowState:
        claims = [
            ResearchClaim(
                text=source.snippet,
                evidence=[source.title],
                confidence=source.credibility_score,
            )
            for source in state.all_sources
        ]
        self._complete_step(state.task, "ExtractClaimsNode", {"claim_count": len(claims)})
        return WorkflowState(
            task=state.task,
            local_sources=state.local_sources,
            web_sources=state.web_sources,
            all_sources=state.all_sources,
            claims=claims,
            report=state.report,
        )

    def _cross_check(self, state: WorkflowState) -> WorkflowState:
        checked = [
            claim.model_copy(update={"confidence": min(claim.confidence + 0.05, 1.0)})
            for claim in state.claims
        ]
        self._complete_step(state.task, "CrossCheckNode", {"claim_count": len(checked)})
        return WorkflowState(
            task=state.task,
            local_sources=state.local_sources,
            web_sources=state.web_sources,
            all_sources=state.all_sources,
            claims=checked,
            report=state.report,
        )

    def _generate_report(self, state: WorkflowState) -> WorkflowState:
        report = ResearchReport(
            summary=f"围绕“{state.task.question}”形成了基于本地与外部来源的结构化研究结论。",
            background=f"研究任务：{state.task.title}。",
            key_findings=[claim.text for claim in state.claims[:5]] or ["暂无关键发现。"],
            evidence=[evidence for claim in state.claims for evidence in claim.evidence],
            comparison_table=[
                {
                    "source": source.title,
                    "type": source.source_type,
                    "credibility": str(source.credibility_score),
                }
                for source in state.all_sources
            ],
            risks_and_uncertainties=["当前网络搜索为 mock 来源，真实外部证据仍需后续接入验证。"],
            next_steps=["导入报告到知识库后运行实体识别与关系抽取任务。"],
        )
        metadata = dict(state.task.metadata_ or {})
        metadata["report"] = report.model_dump()
        state.task.metadata_ = metadata
        self._complete_step(state.task, "GenerateReportNode", report.model_dump())
        self.session.commit()
        return WorkflowState(
            task=state.task,
            local_sources=state.local_sources,
            web_sources=state.web_sources,
            all_sources=state.all_sources,
            claims=state.claims,
            report=report,
        )

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
