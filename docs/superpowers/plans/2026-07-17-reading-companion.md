# AI 陪读与跨资料佐证 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an evidence-first AI reading companion that proactively marks a document, explains it, and corroborates or challenges it using other persisted workspace material.

**Architecture:** Persist analysis runs, anchored insights, and cross-source corroborations in dedicated tables. A `reading_analysis` task handler uses structured LLM output to create source-anchored insights, then uses a local evidence adapter plus `RagService` to collect candidates and classify their stance. The React reader renders only persisted results and polls the task API; it never calls a model itself.

**Tech Stack:** Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2.x, Alembic, existing `TaskJobProcessor`, React 18, TypeScript, Ant Design, Vitest, Testing Library.

---

## File map

| Path | Responsibility |
|---|---|
| `backend/app/schemas/reading_companion.py` | API, enum, and structured-output contracts. |
| `backend/app/infrastructure/models.py` | SQLAlchemy models for analysis, insight, and corroboration. |
| `backend/alembic/versions/202607170002_reading_companion.py` | Database schema, FKs, indexes, and downgrade. |
| `backend/app/services/reading_companion_prompts.py` | Versioned prompt construction only. |
| `backend/app/services/reading_evidence.py` | Workspace-local candidate retrieval and source normalization. |
| `backend/app/services/reading_companion.py` | Analysis orchestration, anchor validation, persistence, and task handler. |
| `backend/app/services/reading_companion_dependencies.py` | API service assembly from the existing database, RAG, and LLM dependencies. |
| `backend/app/api/v1/documents.py` | Reader payload and analysis trigger for a document. |
| `backend/app/api/v1/reading_companion.py` | Analysis polling, insight action, and research-task endpoints. |
| `backend/app/api/v1/router.py`, `backend/app/main.py` | Route and task-handler registration. |
| `backend/app/services/task_worker.py` | Register the new job type without document extraction/graph side effects. |
| `frontend/src/types/readingCompanion.ts` | Backend-aligned reader and analysis types. |
| `frontend/src/services/readingCompanionApi.ts` | Reader API client. |
| `frontend/src/components/reading/*.tsx` | Outline, markers, insight panel, and corroboration rendering. |
| `frontend/src/pages/ReaderPage.tsx`, `frontend/src/App.tsx`, `frontend/src/pages/LibraryPage.tsx` | Data-driven reading route and entry points. |

## Task 1: Define the schema contracts first

**Files:**
- Create: `backend/app/schemas/reading_companion.py`
- Create: `backend/tests/test_reading_companion_schemas.py`

- [ ] **Step 1: Write failing schema tests for valid output and invalid evidence states.**

```python
from pydantic import ValidationError
import pytest

from app.schemas.reading_companion import (
    InsightKind,
    ReadingInsightDraft,
    ReadingInsightUpdateRequest,
)


def test_reading_insight_draft_requires_a_nonempty_anchor() -> None:
    with pytest.raises(ValidationError):
        ReadingInsightDraft(
            kind=InsightKind.understanding,
            headline="解释术语",
            explanation="解释",
            why_it_matters="帮助理解",
            chunk_id="chunk_1",
            evidence_text="",
            start_offset=0,
            end_offset=1,
            confidence=0.8,
            priority=3,
        )


def test_insight_update_accepts_only_a_user_review_state() -> None:
    assert ReadingInsightUpdateRequest(status="confirmed").status == "confirmed"
    with pytest.raises(ValidationError):
        ReadingInsightUpdateRequest(status="completed")
```

- [ ] **Step 2: Run the schema tests and verify they fail because the module does not exist.**

Run: `cd backend && .venv/bin/python -m pytest tests/test_reading_companion_schemas.py -q`

Expected: collection error for `app.schemas.reading_companion`.

- [ ] **Step 3: Implement the complete schema surface.**

```python
class InsightKind(StrEnum):
    understanding = "understanding"
    impact = "impact"
    risk = "risk"


class EvidenceState(StrEnum):
    corroborated = "corroborated"
    conflicted = "conflicted"
    insufficient = "insufficient"


class CorroborationStance(StrEnum):
    supports = "supports"
    contradicts = "contradicts"
    contextualizes = "contextualizes"


class ReadingInsightDraft(BaseModel):
    kind: InsightKind
    headline: str = Field(min_length=1, max_length=240)
    explanation: str = Field(min_length=1)
    why_it_matters: str = Field(min_length=1)
    chunk_id: str = Field(min_length=1)
    evidence_text: str = Field(min_length=1)
    start_offset: int = Field(ge=0)
    end_offset: int = Field(gt=0)
    confidence: float = Field(ge=0, le=1)
    priority: int = Field(ge=1, le=5)
    theme_ids: list[str] = Field(default_factory=list)
    macro_event_ids: list[str] = Field(default_factory=list)
    entity_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def require_increasing_offsets(self) -> Self:
        if self.end_offset <= self.start_offset:
            raise ValueError("end_offset must be greater than start_offset")
        return self
```

Also define response models for reader payload, task trigger/status, insight response, corroboration response, structured corroboration verdict, and `ReadingInsightUpdateRequest`. Keep `status` in the update request as `Literal["confirmed", "dismissed"]`; user notes are optional and limited to 4,000 characters.

- [ ] **Step 4: Run the schema tests and verify they pass.**

Run: `cd backend && .venv/bin/python -m pytest tests/test_reading_companion_schemas.py -q`

Expected: all schema tests pass.

- [ ] **Step 5: Commit the schema contract.**

```bash
git add backend/app/schemas/reading_companion.py backend/tests/test_reading_companion_schemas.py
git commit -m "feat: add reading companion schemas"
```

## Task 2: Persist analysis, insight, and corroboration records

**Files:**
- Modify: `backend/app/infrastructure/models.py:415-435`
- Create: `backend/alembic/versions/202607170002_reading_companion.py`
- Create: `backend/tests/test_reading_companion_models.py`

- [ ] **Step 1: Write failing persistence tests.**

```python
def test_reading_analysis_keeps_insights_for_one_document_version(db_session: Session) -> None:
    analysis = ReadingAnalysis(
        id="ra_1", workspace_id="ws_test", document_id="doc_1", version_id="ver_1"
    )
    insight = ReadingInsight(
        id="ri_1", analysis_id="ra_1", kind="risk", headline="证据不足",
        explanation="来源仅为单一观点", why_it_matters="结论需要复核",
        chunk_id="chunk_1", start_offset=0, end_offset=8, evidence_text="单一观点",
        confidence=0.7, priority=4, evidence_state="insufficient"
    )
    db_session.add_all([analysis, insight])
    db_session.commit()

    assert db_session.get(ReadingInsight, "ri_1").analysis_id == "ra_1"
```

- [ ] **Step 2: Run the model test and verify it fails because the models are unavailable.**

Run: `cd backend && .venv/bin/python -m pytest tests/test_reading_companion_models.py -q`

Expected: import error for `ReadingAnalysis` and `ReadingInsight`.

- [ ] **Step 3: Add SQLAlchemy models and migration.**

Add `ReadingAnalysis`, `ReadingInsight`, and `ReadingCorroboration` after `TaskJob`. Use `String(64)` IDs and workspace/document/version foreign keys consistent with existing models. Add:

```python
class ReadingAnalysis(UpdatedTimestampMixin, Base):
    __tablename__ = "reading_analysis"
    __table_args__ = (
        UniqueConstraint("document_id", "version_id", name="uq_reading_analysis_version"),
        Index("idx_reading_analysis_workspace_status", "workspace_id", "status"),
    )
    # id, workspace_id, document_id, version_id, status, model_name,
    # prompt_version, error_message, completed_at
```

Give `reading_insight` an `idx_reading_insight_analysis_priority` index on `(analysis_id, priority)` and `reading_corroboration` an index on `insight_id`. In the Alembic upgrade, create the three tables before indexes; in downgrade, drop corroboration, insight, then analysis tables and their indexes.

- [ ] **Step 4: Run model and migration-adjacent tests.**

Run: `cd backend && .venv/bin/python -m pytest tests/test_reading_companion_models.py tests/test_database.py -q`

Expected: all tests pass.

- [ ] **Step 5: Commit persisted model support.**

```bash
git add backend/app/infrastructure/models.py backend/alembic/versions/202607170002_reading_companion.py backend/tests/test_reading_companion_models.py
git commit -m "feat: persist reading analyses and evidence"
```

## Task 3: Build a workspace-local evidence adapter

**Files:**
- Create: `backend/app/services/reading_evidence.py`
- Create: `backend/tests/test_reading_evidence.py`

- [ ] **Step 1: Write failing tests for scope, self-exclusion, and source normalization.**

```python
def test_evidence_adapter_excludes_the_current_chunk_and_other_workspaces(
    db_session: Session,
) -> None:
    adapter = ReadingEvidenceAdapter(db_session, rag_service=build_rag(db_session))

    candidates = adapter.search(
        workspace_id="ws_a",
        query="GPU demand",
        excluded_chunk_ids={"chunk_current"},
    )

    assert {candidate.chunk_id for candidate in candidates}.isdisjoint({"chunk_current"})
    assert all(candidate.workspace_id == "ws_a" for candidate in candidates)
```

- [ ] **Step 2: Run the adapter test and verify it fails because the adapter is absent.**

Run: `cd backend && .venv/bin/python -m pytest tests/test_reading_evidence.py -q`

Expected: collection error for `ReadingEvidenceAdapter`.

- [ ] **Step 3: Implement normalized, local-only evidence retrieval.**

Define a `ReadingEvidenceCandidate` dataclass with `source_kind`, `source_id`, `workspace_id`, `document_id`, `chunk_id`, `title`, `excerpt`, `published_at`, and `retrieval_score`. Implement:

```python
class ReadingEvidenceAdapter:
    def search(
        self,
        *,
        workspace_id: str,
        query: str,
        excluded_chunk_ids: set[str],
        limit: int = 12,
    ) -> list[ReadingEvidenceCandidate]:
        document_hits = self._document_hits(workspace_id, query, excluded_chunk_ids, limit)
        investment_hits = self._investment_hits(workspace_id, query, limit)
        macro_hits = self._macro_hits(workspace_id, query, limit)
        return _dedupe_and_limit([*document_hits, *investment_hits, *macro_hits], limit)
```

`_document_hits` must consume `RagService.search` and preserve document/chunk references. `_investment_hits` must query `InvestmentItem`, `InvestmentFact`, `InvestmentSignal`, and `InvestmentClaim` only for the requested workspace. `_macro_hits` must query `MacroEvent` only for the requested workspace. Do not call web search or include raw transient chat messages.

- [ ] **Step 4: Run the adapter tests.**

Run: `cd backend && .venv/bin/python -m pytest tests/test_reading_evidence.py -q`

Expected: all adapter tests pass.

- [ ] **Step 5: Commit evidence retrieval.**

```bash
git add backend/app/services/reading_evidence.py backend/tests/test_reading_evidence.py
git commit -m "feat: retrieve local reading evidence"
```

## Task 4: Implement structured companion analysis and anchoring

**Files:**
- Create: `backend/app/services/reading_companion_prompts.py`
- Create: `backend/app/services/reading_companion.py`
- Create: `backend/tests/test_reading_companion_service.py`

- [ ] **Step 1: Write failing service tests for anchors, insufficient evidence, and conflicting evidence.**

```python
def test_analysis_rejects_an_insight_with_an_anchor_outside_its_chunk(service: ReadingCompanionService) -> None:
    draft = ReadingInsightDraft(
        kind="understanding", headline="错误锚点", explanation="x", why_it_matters="y",
        chunk_id="chunk_1", evidence_text="不存在的文本", start_offset=0, end_offset=6,
        confidence=0.8, priority=3,
    )

    assert service.validate_anchor(chunk_content="真实内容", draft=draft) is None


def test_analysis_marks_insight_insufficient_when_no_candidate_directly_supports_it(
    service: ReadingCompanionService,
) -> None:
    insight = service.run_analysis("ra_1")

    assert insight[0].evidence_state == "insufficient"
    assert insight[0].corroborations == []
```

- [ ] **Step 2: Run the service tests and verify the module is absent.**

Run: `cd backend && .venv/bin/python -m pytest tests/test_reading_companion_service.py -q`

Expected: collection error for `ReadingCompanionService`.

- [ ] **Step 3: Implement prompts and the analysis service.**

Prompts must be built in `reading_companion_prompts.py`, include `PROMPT_VERSION = "reading-companion-v1"`, forbid financial advice, require source anchoring, and tell the model to emit no more than three insights per chunk.

Implement these service methods:

```python
class ReadingCompanionService:
    def create_or_reuse_analysis(self, document_id: str) -> tuple[ReadingAnalysis, TaskJob]: ...
    def get_reader_payload(self, document_id: str) -> ReaderDocumentResponse: ...
    def get_analysis(self, analysis_id: str) -> ReadingAnalysisResponse: ...
    def update_insight(self, insight_id: str, request: ReadingInsightUpdateRequest) -> ReadingInsightResponse: ...
    def run_analysis(self, analysis_id: str) -> list[ReadingInsight]: ...
    def validate_anchor(self, chunk_content: str, draft: ReadingInsightDraft) -> tuple[int, int] | None: ...
```

`create_or_reuse_analysis` reads `document.metadata_["current_version_id"]`, returns an existing `pending` or `running` job for that version, otherwise creates a `TaskJob(job_type="reading_analysis", target_type="reading_analysis", target_id=analysis.id, input={"analysis_id": analysis.id, "document_id": document.id, "version_id": version.id})`. `run_analysis` only persists drafts whose anchored text exists at the claimed offset or at a unique fallback match. It asks `ReadingEvidenceAdapter` for candidates, sends only those candidates to the corroboration schema, and assigns `corroborated`, `conflicted`, or `insufficient` based on persisted stances.

Add `ReadingAnalysisJobHandler.handle(job, session, llm_client)` and `register()` to this module. The handler must set analysis status to `running`, `completed`, or `failed`, preserve the error message, and return counts in `TaskJob.output`.

- [ ] **Step 4: Run the focused service tests.**

Run: `cd backend && .venv/bin/python -m pytest tests/test_reading_companion_service.py -q`

Expected: all service tests pass.

- [ ] **Step 5: Commit analysis orchestration.**

```bash
git add backend/app/services/reading_companion.py backend/app/services/reading_companion_prompts.py backend/tests/test_reading_companion_service.py
git commit -m "feat: analyze reading insights with evidence"
```

## Task 5: Register the task and expose APIs

**Files:**
- Create: `backend/app/services/reading_companion_dependencies.py`
- Create: `backend/app/api/v1/reading_companion.py`
- Modify: `backend/app/api/v1/documents.py:1-110`
- Modify: `backend/app/api/v1/router.py:1-28`
- Modify: `backend/app/main.py:215-245`
- Modify: `backend/app/services/task_worker.py:38-200`
- Create: `backend/tests/test_reading_companion_api.py`
- Create: `backend/tests/test_reading_companion_integration.py`

- [ ] **Step 1: Write failing API tests.**

```python
def test_reader_payload_and_analysis_trigger_are_idempotent(client: TestClient) -> None:
    first = client.post("/api/v1/documents/doc_1/reading-analyses")
    second = client.post("/api/v1/documents/doc_1/reading-analyses")

    assert first.status_code == 200
    assert second.json()["analysis_id"] == first.json()["analysis_id"]
    assert second.json()["task_job_id"] == first.json()["task_job_id"]


def test_insight_update_and_research_task_keep_workspace_scope(client: TestClient) -> None:
    response = client.patch(
        "/api/v1/reading-insights/ri_1", json={"status": "confirmed", "note": "待跟踪"}
    )
    assert response.status_code == 200
    assert response.json()["status"] == "confirmed"


def test_reading_analysis_job_persists_anchored_insights_and_corroborations(
    db_session: Session,
) -> None:
    processor = TaskJobProcessor(
        session_factory=session_factory_for(db_session),
        llm_client=scripted_reading_llm(),
        graph_store=None,
    )

    assert processor.run_once() == 1
    assert db_session.get(ReadingAnalysis, "ra_1").status == "completed"
    assert db_session.scalar(select(ReadingCorroboration)) is not None
```

- [ ] **Step 2: Run API tests and verify they fail with 404 routes.**

Run: `cd backend && .venv/bin/python -m pytest tests/test_reading_companion_api.py -q`

Expected: endpoint tests fail with 404 and the task integration test fails because `reading_analysis` has no registered handler.

- [ ] **Step 3: Assemble dependencies, routes, and worker registration.**

`get_reading_companion_service` constructs the service with the request `Session`, `get_rag_service()` dependencies, `build_llm_client_from_settings()`, and `ReadingEvidenceAdapter`. Add:

```python
@router.get("/{doc_id}/reader", response_model=ReaderDocumentResponse)
async def get_reader_document(...):
    return companion_service.get_reader_payload(doc_id)

@router.post("/{doc_id}/reading-analyses", response_model=ReadingAnalysisTriggerResponse)
async def trigger_reading_analysis(...):
    analysis, job = companion_service.create_or_reuse_analysis(doc_id)
    return ReadingAnalysisTriggerResponse(analysis_id=analysis.id, task_job_id=job.id, status=job.status)
```

Use `reading_companion.py` for `GET /reading-analyses/{analysis_id}`, `PATCH /reading-insights/{insight_id}`, and `POST /reading-insights/{insight_id}/research-tasks`. The research-task endpoint must call the existing `ResearchAgentService.create_task` with a question constructed from the insight headline, explanation, and explicitly selected corroborations.

In `main.lifespan`, call `register_reading_companion_handler()` before starting the task scheduler. In `task_worker.py`, keep `reading_analysis` out of `_DOC_STATUS_FIELD` and out of graph synchronization; it is document-scoped but does not represent entity/relation extraction.

- [ ] **Step 4: Run API and worker tests.**

Run: `cd backend && .venv/bin/python -m pytest tests/test_reading_companion_api.py tests/test_reading_companion_integration.py tests/test_task_worker.py -q`

Expected: all tests pass.

- [ ] **Step 5: Commit APIs and async wiring.**

```bash
git add backend/app/services/reading_companion_dependencies.py backend/app/api/v1/reading_companion.py backend/app/api/v1/documents.py backend/app/api/v1/router.py backend/app/main.py backend/app/services/task_worker.py backend/tests/test_reading_companion_api.py backend/tests/test_reading_companion_integration.py
git commit -m "feat: expose reading companion APIs"
```

## Task 6: Add frontend types and API client

**Files:**
- Create: `frontend/src/types/readingCompanion.ts`
- Create: `frontend/src/services/readingCompanionApi.ts`
- Create: `frontend/src/services/readingCompanionApi.test.ts`

- [ ] **Step 1: Write failing API-client tests.**

```tsx
it("triggers analysis with the document endpoint", async () => {
  vi.stubGlobal("fetch", vi.fn(async () => Response.json({
    analysis_id: "ra_1", task_job_id: "job_1", status: "pending",
  })));

  await readingCompanionApi.trigger("doc_1");

  expect(fetch).toHaveBeenCalledWith(
    "/api/v1/documents/doc_1/reading-analyses",
    expect.objectContaining({ method: "POST" }),
  );
});
```

- [ ] **Step 2: Run the client test and verify it fails because the client is absent.**

Run: `cd frontend && npm run test -- readingCompanionApi.test.ts`

Expected: module-resolution failure.

- [ ] **Step 3: Implement types and API functions.**

Define discriminated string unions matching backend `kind`, `evidence_state`, `stance`, and `status`. Implement `getReader`, `trigger`, `getAnalysis`, `updateInsight`, and `createResearchTask` through `apiRequest`; do not duplicate fetch/error parsing logic.

- [ ] **Step 4: Run the frontend client test.**

Run: `cd frontend && npm run test -- readingCompanionApi.test.ts`

Expected: all tests pass.

- [ ] **Step 5: Commit the frontend API boundary.**

```bash
git add frontend/src/types/readingCompanion.ts frontend/src/services/readingCompanionApi.ts frontend/src/services/readingCompanionApi.test.ts
git commit -m "feat: add reading companion frontend client"
```

## Task 7: Build focused reader presentation components

**Files:**
- Create: `frontend/src/components/reading/DocumentOutline.tsx`
- Create: `frontend/src/components/reading/InsightMarker.tsx`
- Create: `frontend/src/components/reading/InsightPanel.tsx`
- Create: `frontend/src/components/reading/CorroborationList.tsx`
- Create: `frontend/src/components/reading/InsightPanel.test.tsx`

- [ ] **Step 1: Write failing component tests for evidence-state labels and user review actions.**

```tsx
it("shows a conflict card with both supporting and contradictory sources", () => {
  render(<InsightPanel insights={[conflictedInsight]} onUpdate={vi.fn()} onResearch={vi.fn()} />);

  expect(screen.getByText("存在冲突")).toBeInTheDocument();
  expect(screen.getByText("支持证据")).toBeInTheDocument();
  expect(screen.getByText("冲突证据")).toBeInTheDocument();
});

it("confirms an insight without changing its evidence", async () => {
  const onUpdate = vi.fn();
  render(<InsightPanel insights={[understandingInsight]} onUpdate={onUpdate} onResearch={vi.fn()} />);

  await userEvent.click(screen.getByRole("button", { name: "确认" }));
  expect(onUpdate).toHaveBeenCalledWith("ri_1", { status: "confirmed" });
});
```

- [ ] **Step 2: Run the component test and verify it fails because the components are absent.**

Run: `cd frontend && npm run test -- InsightPanel.test.tsx`

Expected: module-resolution failure.

- [ ] **Step 3: Implement pure presentation components.**

`InsightPanel` sorts cards by conflict/risk, corroborated impact, then understanding; it renders `本地资料不足` for `insufficient`. `CorroborationList` groups only persisted `supports`, `contradicts`, and `contextualizes` records and calls a supplied source-navigation callback. `InsightMarker` accepts `kind`, `active`, and `onClick`; it does not infer evidence state from CSS. `DocumentOutline` only navigates to chunks.

- [ ] **Step 4: Run component tests.**

Run: `cd frontend && npm run test -- InsightPanel.test.tsx`

Expected: all component tests pass.

- [ ] **Step 5: Commit reader presentation components.**

```bash
git add frontend/src/components/reading
git commit -m "feat: render reading companion insights"
```

## Task 8: Replace the static reader with a data-driven, responsive flow

**Files:**
- Modify: `frontend/src/pages/ReaderPage.tsx:1-67`
- Create: `frontend/src/pages/ReaderPage.test.tsx`
- Modify: `frontend/src/App.tsx:50-154`
- Modify: `frontend/src/pages/LibraryPage.tsx`
- Modify: `frontend/src/App.test.tsx:1-48`

- [ ] **Step 1: Write failing page tests for loading, pending, completed, and navigation behavior.**

```tsx
it("polls a pending analysis and renders its anchored insight", async () => {
  vi.stubGlobal("fetch", fetchReaderWithPendingThenCompletedAnalysis());
  render(<MemoryRouter initialEntries={["/reader/doc_1"]}><ReaderPage /></MemoryRouter>);

  expect(await screen.findByText("正在分析文档")).toBeInTheDocument();
  expect(await screen.findByText("本地资料不足")).toBeInTheDocument();
  expect(screen.getByText("关键段落")).toBeInTheDocument();
});

it("keeps /reader usable as a document picker", async () => {
  vi.stubGlobal("fetch", fetchDocumentList());
  render(<MemoryRouter initialEntries={["/reader"]}><ReaderPage /></MemoryRouter>);

  expect(await screen.findByText("选择一篇文档开始陪读")).toBeInTheDocument();
});
```

- [ ] **Step 2: Run the page tests and verify they fail against the static reader.**

Run: `cd frontend && npm run test -- ReaderPage.test.tsx`

Expected: assertions fail because no API-backed reader or status UI exists.

- [ ] **Step 3: Implement reader state and routing.**

Use `useParams` and `useNavigate`. Preserve `/reader` as a small document-picker state and add `/reader/:documentId` to `App.tsx`; the sidebar continues to link to `/reader`. On document selection, load `readingCompanionApi.getReader(documentId)`. If status is `pending` or `running`, call `trigger` once only when no job exists, then poll `getAnalysis` every three seconds until terminal. Clear timers on unmount. Render user-facing failures with retry, never discard already completed cards.

Render the document as chunk sections with stable DOM IDs (`chunk-${chunk.id}`), wrap anchored spans with `InsightMarker`, and let marker/card clicks set the active insight and call `scrollIntoView`. On narrow screens, move `InsightPanel` into an Ant Design `Drawer`; do not remove corroboration text. Add a “开始研究” action that calls the insight API and navigates to `/research` after success.

In `LibraryPage`, add an explicit `Link` to `/reader/${document.id}` for each listed document. Update `App.test.tsx` so `/reader` still renders its heading and `/reader/doc_1` is reachable.

- [ ] **Step 4: Run focused reader and app tests.**

Run: `cd frontend && npm run test -- ReaderPage.test.tsx App.test.tsx`

Expected: all reader and route tests pass.

- [ ] **Step 5: Commit the reader experience.**

```bash
git add frontend/src/pages/ReaderPage.tsx frontend/src/pages/ReaderPage.test.tsx frontend/src/pages/LibraryPage.tsx frontend/src/App.tsx frontend/src/App.test.tsx
git commit -m "feat: add proactive AI reading companion"
```

## Task 9: Document local operation and verify the integrated feature

**Files:**
- Modify: `README.md`
- Modify: `docs/development/testing-guide.md`

- [ ] **Step 1: Add only the documentation required to operate the feature locally.**

Document the `reading_analysis` background task, the local-only evidence boundary, model configuration reuse, and the three evidence-state meanings. Add exact backend/frontend test commands to the testing guide.

- [ ] **Step 2: Run all required verification commands.**

Run:

```bash
cd backend && .venv/bin/python -m pytest
cd backend && .venv/bin/ruff check .
cd backend && .venv/bin/mypy app
cd frontend && npm run lint
cd frontend && npm run test
cd frontend && npm run build
```

Expected: every command exits 0. If a pre-existing failure appears, stop and diagnose it separately before claiming completion.

- [ ] **Step 3: Commit documentation and final verification changes.**

```bash
git add README.md docs/development/testing-guide.md
git commit -m "docs: explain reading companion workflow"
```

## Plan self-review

- Spec coverage: Tasks 1–2 implement structured, evidence-backed persistence; Tasks 3–5 implement local corroboration, async processing, workspace isolation, APIs, and research handoff; Tasks 6–8 implement the responsive proactive reader; Task 9 covers operation and all required quality gates.
- Scope: first delivery includes local documents, research, video-derived document content, investment records, and macro events. It deliberately excludes external web search, persistent chat storage, automated trading conclusions, feedback learning, and cross-version comparisons.
- Type consistency: `ReadingInsightDraft`, `ReadingAnalysis`, `ReadingInsight`, `ReadingCorroboration`, `ReadingEvidenceAdapter`, and `ReadingCompanionService` are introduced before later tasks consume them. API and frontend vocabulary use the same `kind`, `evidence_state`, `stance`, and review status values.
