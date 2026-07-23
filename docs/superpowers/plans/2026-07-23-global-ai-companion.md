# Global AI Companion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver one persistent, evidence-grounded AI companion drawer for documents, YouTube summaries, and information-edge items.

**Architecture:** A generic companion domain stores sessions, messages, insights, and citations by typed subject. Backend context adapters load the active subject and workspace evidence; `App.tsx` hosts a global drawer and pages set context descriptors rather than duplicating UI.

**Tech Stack:** FastAPI, Pydantic v2, SQLAlchemy/Alembic, existing `task_job`, React, TypeScript, Ant Design, TanStack Query, pytest, Vitest.

---

### Task 1: Companion schema and persistence

**Files:**
- Create: `backend/alembic/versions/202607230002_global_companion.py`
- Create: `backend/app/schemas/companion.py`
- Modify: `backend/app/infrastructure/models.py`
- Test: `backend/tests/test_companion_models.py`

- [ ] **Step 1: Write failing model tests**

```python
def test_companion_session_is_unique_per_subject(session: Session) -> None:
    first = CompanionSession(id="cs_1", workspace_id="ws_default", subject_type="youtube_video", subject_id="video_1", title="Video")
    second = CompanionSession(id="cs_2", workspace_id="ws_default", subject_type="youtube_video", subject_id="video_1", title="Video")
    session.add(first)
    session.commit()
    session.add(second)
    with pytest.raises(IntegrityError):
        session.commit()
```

- [ ] **Step 2: Run failing test**

Run: `cd backend && pytest tests/test_companion_models.py::test_companion_session_is_unique_per_subject -v`

Expected: FAIL because companion models do not exist.

- [ ] **Step 3: Implement models, migration, and Pydantic contracts**

Create `CompanionSession`, `CompanionMessage`, and `CompanionInsight` with
`workspace_id`, `subject_type`, `subject_id`, JSON citations, confidence,
status, and timestamps. Use `UniqueConstraint("workspace_id", "subject_type",
"subject_id", name="uq_companion_session_subject")`. Add corresponding
Pydantic create/response schemas before service code.

- [ ] **Step 4: Verify and commit**

Run: `cd backend && pytest tests/test_companion_models.py -v && alembic heads`

```bash
git add backend/alembic/versions/202607230002_global_companion.py backend/app/infrastructure/models.py backend/app/schemas/companion.py backend/tests/test_companion_models.py
git commit -m "feat: persist global companion sessions"
```

### Task 2: Subject context and evidence service

**Files:**
- Create: `backend/app/services/companion/context.py`
- Create: `backend/app/services/companion/service.py`
- Test: `backend/tests/test_companion_service.py`

- [ ] **Step 1: Write failing context tests**

```python
def test_video_context_includes_summary_and_internal_evidence(session: Session) -> None:
    context = CompanionContextService(session).load("ws_default", "youtube_video", "video_1")
    assert context.primary.title == "Video title"
    assert context.evidence[0].relation == "primary"
```

- [ ] **Step 2: Run failing test**

Run: `cd backend && pytest tests/test_companion_service.py::test_video_context_includes_summary_and_internal_evidence -v`

Expected: FAIL because `CompanionContextService` does not exist.

- [ ] **Step 3: Implement typed context adapters**

Define `CompanionSubjectType = Literal["document", "youtube_video",
"information_edge", "workspace"]`. `load()` validates subject ownership,
loads primary source material, then calls existing workspace retrieval for
corroborating/conflicting chunks. Return structured evidence with `source_id`,
`source_title`, `excerpt`, `location`, `relation`, and `confidence`. Raise a
typed not-found error rather than silently switching workspaces.

- [ ] **Step 4: Add proactive and chat operations**

`CompanionService.create_or_reuse_session()` creates one session per subject.
`submit_message()` persists the user message, invokes structured LLM output,
and persists an assistant message with citations. `create_or_reuse_insights()`
creates a `task_job`; its handler writes bounded focus/question/risk/opportunity
insights and preserves prior completed insights on refresh failure.

- [ ] **Step 5: Verify and commit**

Run: `cd backend && pytest tests/test_companion_service.py -v`

```bash
git add backend/app/services/companion backend/tests/test_companion_service.py
git commit -m "feat: add evidence-grounded companion service"
```

### Task 3: Companion API and worker registration

**Files:**
- Create: `backend/app/api/v1/companion.py`
- Modify: `backend/app/api/v1/router.py`
- Modify: `backend/app/services/task_worker.py` or companion handler registration module
- Test: `backend/tests/test_companion_api.py`

- [ ] **Step 1: Write failing API test**

```python
def test_companion_message_persists_for_video_subject(client: TestClient) -> None:
    response = client.post("/api/v1/companion/sessions", json={"workspace_id": "ws_default", "subject_type": "youtube_video", "subject_id": "video_1"})
    assert response.status_code == 200
    session_id = response.json()["id"]
    reply = client.post(f"/api/v1/companion/sessions/{session_id}/messages", json={"content": "这个结论有什么证据？"})
    assert reply.status_code == 200
    assert reply.json()["citations"]
```

- [ ] **Step 2: Run failing API test**

Run: `cd backend && pytest tests/test_companion_api.py::test_companion_message_persists_for_video_subject -v`

Expected: FAIL with 404 because the router is not registered.

- [ ] **Step 3: Implement API**

Expose session create/list/get, message submit, proactive insight trigger/get,
and insight review endpoints under `/api/v1/companion`. Validate subject and
workspace through `CompanionContextService`; use response schemas that always
include citations and confidence.

- [ ] **Step 4: Verify and commit**

Run: `cd backend && pytest tests/test_companion_api.py -v && ruff check app/api/v1/companion.py app/services/companion`

```bash
git add backend/app/api/v1/companion.py backend/app/api/v1/router.py backend/app/services backend/tests/test_companion_api.py
git commit -m "feat: expose global companion APIs"
```

### Task 4: Global drawer and context provider

**Files:**
- Create: `frontend/src/components/companion/CompanionDrawer.tsx`
- Create: `frontend/src/components/companion/CompanionProvider.tsx`
- Create: `frontend/src/services/companionApi.ts`
- Create: `frontend/src/types/companion.ts`
- Modify: `frontend/src/App.tsx`
- Test: `frontend/src/components/companion/CompanionDrawer.test.tsx`

- [ ] **Step 1: Write failing component test**

```tsx
it("opens with the active video context and sends a saved question", async () => {
  render(<CompanionProvider initialContext={videoContext}><CompanionDrawer /></CompanionProvider>);
  fireEvent.click(screen.getByRole("button", { name: "AI 陪读" }));
  expect(screen.getByText("视频：Video title")).toBeInTheDocument();
  fireEvent.change(screen.getByPlaceholderText("围绕当前内容提问…"), { target: { value: "有哪些反证？" } });
  fireEvent.click(screen.getByRole("button", { name: "发送" }));
  expect(await screen.findByText("平台内佐证")).toBeInTheDocument();
});
```

- [ ] **Step 2: Run failing test**

Run: `cd frontend && npm run test -- CompanionDrawer.test.tsx`

Expected: FAIL because drawer/provider do not exist.

- [ ] **Step 3: Implement provider and drawer**

Provider exposes `setContext`, `clearContext`, and `open`. The drawer renders a
single floating trigger, context pill, proactive insights, citations with
confidence, persisted messages, new-session action, and retry state. `App.tsx`
wraps routes once so there is no page-specific drawer duplication.

- [ ] **Step 4: Verify and commit**

Run: `cd frontend && npm run test -- CompanionDrawer.test.tsx && npm run lint`

```bash
git add frontend/src/components/companion frontend/src/services/companionApi.ts frontend/src/types/companion.ts frontend/src/App.tsx
git commit -m "feat: add global companion drawer"
```

### Task 5: Page adapters and reader migration

**Files:**
- Modify: `frontend/src/pages/ReaderPage.tsx`
- Modify: `frontend/src/pages/VideoSummaryPage.tsx`
- Modify: `frontend/src/pages/InformationEdgePage.tsx`
- Modify: `frontend/src/pages/ReaderPage.test.tsx`
- Modify: `frontend/src/pages/VideoSummaryPage.test.tsx`
- Modify: `frontend/src/pages/InformationEdgePage.test.tsx`

- [ ] **Step 1: Write failing route-context tests**

```tsx
it("sets video context when a video summary is loaded", async () => {
  renderVideoSummary();
  expect(await screen.findByText("Video title")).toBeInTheDocument();
  expect(mockSetContext).toHaveBeenCalledWith(expect.objectContaining({ subjectType: "youtube_video" }));
});
```

- [ ] **Step 2: Run the focused test to verify it fails**

Run: `cd frontend && npm run test -- VideoSummaryPage.test.tsx`

Expected: FAIL because pages do not register companion context.

- [ ] **Step 3: Implement adapters**

Reader sets document context and replaces its local right-rail analysis with an
`打开 AI 陪读` action. Video detail sets video context after loading the card.
Information edge sets page context from filters and switches to a selected
edge context when the user activates a card. Each cleanup clears only the
matching context.

- [ ] **Step 4: Verify and commit**

Run: `cd frontend && npm run test -- ReaderPage.test.tsx VideoSummaryPage.test.tsx InformationEdgePage.test.tsx`

```bash
git add frontend/src/pages
git commit -m "feat: connect companion to content pages"
```

### Task 6: Full verification and migration documentation

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Document the global companion entry and evidence behavior**

Add a README section stating that AI 陪读 is available from the global drawer,
saves subject-scoped conversations, and cites internal evidence.

- [ ] **Step 2: Run all verification**

```bash
cd backend && pytest && ruff check . && alembic upgrade head
cd ../frontend && npm run test && npm run lint && npm run build
```

- [ ] **Step 3: Commit documentation**

```bash
git add README.md
git commit -m "docs: describe global AI companion"
```
