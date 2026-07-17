# 模型管理 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add secure, database-backed management and runtime routing for LLM, Embedding, ASR, and OCR models.

**Architecture:** Keep the existing provider/model tables, extend provider records with encrypted credential and test state, and add a one-row-per-capability route table. A typed model-management service owns CRUD, validation, encryption, tests, and resolution; API factories and workers receive clients from that resolver, falling back to existing environment settings only when no database route exists.

**Tech Stack:** FastAPI, Pydantic v2, SQLAlchemy 2.x, Alembic, `cryptography.fernet`, httpx/OpenAI SDK, React, TypeScript, Ant Design, Vitest.

---

## File map

- Create `backend/app/schemas/model_management.py`: request/response schemas and model capability/protocol enums.
- Create `backend/app/services/model_crypto.py`: Fernet encryption, masking and configuration error boundary.
- Create `backend/app/services/model_management.py`: provider/model/route CRUD, validation and safe API views.
- Create `backend/app/services/model_connection_test.py`: protocol-specific test request adapters and result classification.
- Create `backend/app/services/model_runtime.py`: resolve default database routes into LLM/Embedding/ASR/OCR client configurations.
- Create `backend/app/api/v1/model_management.py`: HTTP endpoints with typed dependencies.
- Create `backend/alembic/versions/202607170003_model_management.py`: additive database migration.
- Create `backend/tests/test_model_management.py`, `backend/tests/test_model_connection_test.py`, `backend/tests/test_model_runtime.py`, `backend/tests/test_model_management_api.py`.
- Modify `backend/app/core/config.py`, `backend/app/infrastructure/models.py`, `backend/app/api/v1/router.py`.
- Modify `backend/app/services/research_dependencies.py`, `backend/app/services/rag_dependencies.py`, `backend/app/services/youtube/asr.py`, `backend/app/services/youtube/visual_analysis.py`, `backend/app/services/youtube/summary_job_handler.py`, `backend/app/api/v1/youtube.py`, `backend/app/api/v1/entities.py`, `backend/app/api/v1/investment.py`, `backend/app/services/task_worker_dependencies.py`, `backend/app/services/reading_companion_dependencies.py`, and `backend/app/main.py` to pass a session to the resolver.
- Create `frontend/src/types/modelManagement.ts` and `frontend/src/services/modelManagementApi.ts`.
- Create `frontend/src/pages/ModelManagementPage.tsx` and `frontend/src/pages/ModelManagementPage.test.tsx`.
- Modify `frontend/src/App.tsx` and `frontend/src/pages/SettingsPage.tsx` to make model management reachable from Settings.
- Modify `.env.example` and `README.md` with `MODEL_ENCRYPTION_KEY` deployment guidance; no real secret is committed.

### Task 1: Freeze schemas and persistent model routing

**Files:**
- Create: `backend/app/schemas/model_management.py`
- Modify: `backend/app/infrastructure/models.py`
- Create: `backend/alembic/versions/202607170003_model_management.py`
- Test: `backend/tests/test_model_management.py`

- [ ] **Step 1: Write failing schema/model tests**

```python
def test_model_route_requires_matching_enabled_capability(db_session: Session) -> None:
    provider = ModelProvider(id="provider_1", name="OpenAI", provider_type="openai_compatible")
    llm = ModelConfig(id="llm_1", provider_id=provider.id, model_name="gpt", model_type="llm")
    embedding = ModelConfig(id="embedding_1", provider_id=provider.id, model_name="embed", model_type="embedding")
    db_session.add_all([provider, llm, embedding])
    db_session.commit()

    with pytest.raises(ModelRouteValidationError, match="capability"):
        ModelManagementService(db_session).set_route("llm", embedding.id)
```

- [ ] **Step 2: Run the failing test**

Run: `cd backend && .venv/bin/python -m pytest tests/test_model_management.py -v`
Expected: FAIL because schemas, `ModelRoute`, and `ModelManagementService` do not exist.

- [ ] **Step 3: Add typed schema and SQLAlchemy models**

```python
class ModelCapability(str, Enum):
    LLM = "llm"
    EMBEDDING = "embedding"
    ASR = "asr"
    OCR = "ocr"

class ProviderProtocol(str, Enum):
    OPENAI_COMPATIBLE = "openai_compatible"
    GLM_ASR = "glm_asr"
    KNOWPILOT_OCR = "knowpilot_ocr"

class ModelRoute(TimestampMixin, Base):
    __tablename__ = "model_route"
    __table_args__ = (UniqueConstraint("capability", name="uq_model_route_capability"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    capability: Mapped[str] = mapped_column(String(32), nullable=False)
    model_config_id: Mapped[str] = mapped_column(ForeignKey("model_config.id"), nullable=False)
    model_config: Mapped[ModelConfig] = relationship()
```

Extend `ModelProvider` with nullable `api_key_ciphertext`, `api_key_hint`, `timeout_seconds`, `last_test_status`, `last_test_message`, and `last_tested_at`; preserve legacy `api_key_ref` without reading or writing it in the new service. Create an additive Alembic migration with `down_revision = "202607170002"`.

- [ ] **Step 4: Re-run model tests and migration smoke test**

Run: `cd backend && .venv/bin/python -m pytest tests/test_model_management.py -v && .venv/bin/alembic upgrade head`
Expected: passing test and successful migration.

- [ ] **Step 5: Commit the data contract**

```bash
git add backend/app/schemas/model_management.py backend/app/infrastructure/models.py \
  backend/alembic/versions/202607170003_model_management.py backend/tests/test_model_management.py
git commit -m "feat: add model management data schema"
```

### Task 2: Encrypt credentials and implement provider/model/route service

**Files:**
- Create: `backend/app/services/model_crypto.py`
- Create: `backend/app/services/model_management.py`
- Modify: `backend/app/core/config.py`
- Test: `backend/tests/test_model_management.py`

- [ ] **Step 1: Add failing credential behavior tests**

```python
def test_provider_key_is_encrypted_and_response_only_exposes_mask(db_session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MODEL_ENCRYPTION_KEY", Fernet.generate_key().decode())
    get_settings.cache_clear()
    saved = ModelManagementService(db_session).create_provider(
        ProviderCreate(name="DeepSeek", provider_type="openai_compatible", base_url="https://api.example", api_key="sk-secret-1234")
    )
    stored = db_session.get(ModelProvider, saved.id)
    assert stored.api_key_ciphertext != "sk-secret-1234"
    assert saved.api_key_configured is True
    assert saved.api_key_hint.endswith("1234")
    assert "secret" not in saved.model_dump_json()
```

- [ ] **Step 2: Run the failing credential test**

Run: `cd backend && .venv/bin/python -m pytest tests/test_model_management.py::test_provider_key_is_encrypted_and_response_only_exposes_mask -v`
Expected: FAIL because encryption and safe response conversion are absent.

- [ ] **Step 3: Implement Fernet helpers and service invariants**

```python
def encrypt_api_key(value: str, settings: Settings) -> str:
    if not settings.model_encryption_key:
        raise AppError("model_encryption_not_configured", "MODEL_ENCRYPTION_KEY is required.", 503)
    return Fernet(settings.model_encryption_key.encode()).encrypt(value.encode()).decode()

def mask_api_key(value: str) -> str:
    return f"{value[:3]}…{value[-4:]}" if len(value) > 7 else "已配置"
```

`ModelManagementService` must reject route targets whose provider/model is disabled or whose `model_type` differs from `capability`; return 409 for deleting an active route target or a provider that still owns models. Updating a provider with `api_key=None` preserves its existing ciphertext.

- [ ] **Step 4: Re-run service tests**

Run: `cd backend && .venv/bin/python -m pytest tests/test_model_management.py -v`
Expected: PASS, including encrypt, mask, route and delete constraint cases.

- [ ] **Step 5: Commit credential service**

```bash
git add backend/app/core/config.py backend/app/services/model_crypto.py \
  backend/app/services/model_management.py backend/tests/test_model_management.py
git commit -m "feat: secure managed model credentials"
```

### Task 3: Add protocol-aware connection tests

**Files:**
- Create: `backend/app/services/model_connection_test.py`
- Test: `backend/tests/test_model_connection_test.py`

- [ ] **Step 1: Write failing request-construction and error-classification tests**

```python
def test_openai_embedding_connection_test_posts_minimal_embedding() -> None:
    http = RecordingHttpClient(status_code=200, payload={"data": [{"embedding": [0.1]}]})
    result = ModelConnectionTester(http_client=http).test(ProviderTestRequest(
        provider_type="openai_compatible", base_url="https://api.example/v1", api_key="sk-test", model_name="text-embedding-3-small", capability="embedding"
    ))
    assert http.requests[0].url == "https://api.example/v1/embeddings"
    assert result.status == "success"

def test_connection_test_classifies_401_as_authentication_failure() -> None:
    result = ModelConnectionTester(http_client=failing_client(401)).test(llm_request())
    assert result.status == "authentication_failed"
```

- [ ] **Step 2: Run the failing connection tests**

Run: `cd backend && .venv/bin/python -m pytest tests/test_model_connection_test.py -v`
Expected: FAIL because `ModelConnectionTester` does not exist.

- [ ] **Step 3: Implement adapters without logging secrets**

Use `POST /chat/completions` with a one-token LLM request, `POST /embeddings` for embeddings, a generated short WAV multipart request for GLM ASR, and a generated 1×1 PNG multipart `POST /ocr` for KnowPilot OCR. Map 401/403 to `authentication_failed`, 404/405 and invalid payloads to `protocol_error`, timeout/transport errors to `connection_failed`, and known model errors to `capability_mismatch`.

- [ ] **Step 4: Re-run test adapter suite**

Run: `cd backend && .venv/bin/python -m pytest tests/test_model_connection_test.py -v`
Expected: PASS with no outbound network requests.

- [ ] **Step 5: Commit connection tests**

```bash
git add backend/app/services/model_connection_test.py backend/tests/test_model_connection_test.py
git commit -m "feat: test managed model connections"
```

### Task 4: Expose model-management HTTP API

**Files:**
- Create: `backend/app/api/v1/model_management.py`
- Modify: `backend/app/api/v1/router.py`
- Test: `backend/tests/test_model_management_api.py`

- [ ] **Step 1: Write failing API behavior tests**

```python
def test_provider_api_never_returns_plaintext_key(client: TestClient) -> None:
    created = client.post("/api/v1/model-management/providers", json={
        "name": "Provider", "provider_type": "openai_compatible", "base_url": "https://api.example", "api_key": "sk-private-key"
    })
    assert created.status_code == 201
    assert created.json()["api_key_configured"] is True
    assert "sk-private-key" not in created.text

def test_deleting_routed_model_returns_conflict(client: TestClient) -> None:
    model_id = create_routed_llm(client)
    response = client.delete(f"/api/v1/model-management/models/{model_id}")
    assert response.status_code == 409
```

- [ ] **Step 2: Run the failing API tests**

Run: `cd backend && .venv/bin/python -m pytest tests/test_model_management_api.py -v`
Expected: FAIL with route not found.

- [ ] **Step 3: Implement CRUD, test, and route endpoints**

```python
router = APIRouter(prefix="/model-management", tags=["model-management"])

@router.post("/providers", response_model=ModelProviderResponse, status_code=201)
def create_provider(payload: ProviderCreate, session: Session = Depends(get_db_session)) -> ModelProviderResponse:
    return ModelManagementService(session).create_provider(payload)

@router.post("/providers/test", response_model=ConnectionTestResult)
def test_provider(payload: ProviderTestRequest) -> ConnectionTestResult:
    return ModelConnectionTester().test(payload)
```

Include every endpoint listed in the approved specification, route all domain errors through `AppError`, and register the router in `api_router`.

- [ ] **Step 4: Re-run model-management API tests**

Run: `cd backend && .venv/bin/python -m pytest tests/test_model_management_api.py -v`
Expected: PASS for CRUD, safe key projection, conflict and connection-test responses.

- [ ] **Step 5: Commit the HTTP boundary**

```bash
git add backend/app/api/v1/model_management.py backend/app/api/v1/router.py backend/tests/test_model_management_api.py
git commit -m "feat: expose model management API"
```

### Task 5: Resolve runtime clients from database routes

**Files:**
- Create: `backend/app/services/model_runtime.py`
- Modify: `backend/app/services/research_dependencies.py`
- Modify: `backend/app/services/rag_dependencies.py`
- Modify: `backend/app/services/youtube/asr.py`
- Modify: `backend/app/services/youtube/visual_analysis.py`
- Test: `backend/tests/test_model_runtime.py`

- [ ] **Step 1: Write failing database-priority and environment-fallback tests**

```python
def test_llm_runtime_uses_database_route_before_environment(db_session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    configure_routed_model(db_session, capability="llm", model_name="managed-llm")
    monkeypatch.setenv("LLM_MODEL", "env-llm")
    client = ModelRuntimeResolver(db_session).build_llm_client()
    assert client.model == "managed-llm"

def test_unconfigured_embedding_route_uses_existing_env_fallback(db_session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")
    assert ModelRuntimeResolver(db_session).build_embedding_client().__class__.__name__ == "MockEmbeddingClient"
```

- [ ] **Step 2: Run the failing runtime tests**

Run: `cd backend && .venv/bin/python -m pytest tests/test_model_runtime.py -v`
Expected: FAIL because the resolver is absent and factories do not accept a database session.

- [ ] **Step 3: Implement one resolver and adapt factories**

```python
class ModelRuntimeResolver:
    def build_llm_client(self) -> StructuredOutputClient: ...
    def build_embedding_client(self) -> EmbeddingClient: ...
    def build_asr_service(self) -> AsrService | None: ...
    def build_ocr_client(self) -> OcrClient | None: ...
```

Resolver methods load an enabled default route, decrypt its provider key only while constructing the client, and otherwise call the existing `.env` factory. Change the existing factories to accept an optional `Session`; the no-session paths retain existing behavior for compatibility.

- [ ] **Step 4: Re-run runtime tests**

Run: `cd backend && .venv/bin/python -m pytest tests/test_model_runtime.py -v`
Expected: PASS for all four capability types and environment fallback.

- [ ] **Step 5: Commit resolver integration**

```bash
git add backend/app/services/model_runtime.py backend/app/services/research_dependencies.py \
  backend/app/services/rag_dependencies.py backend/app/services/youtube/asr.py \
  backend/app/services/youtube/visual_analysis.py backend/tests/test_model_runtime.py
git commit -m "feat: resolve AI clients from managed models"
```

### Task 6: Route every current AI workload through the resolver

**Files:**
- Modify: `backend/app/api/v1/entities.py`
- Modify: `backend/app/api/v1/investment.py`
- Modify: `backend/app/api/v1/youtube.py`
- Modify: `backend/app/services/task_worker_dependencies.py`
- Modify: `backend/app/services/reading_companion_dependencies.py`
- Modify: `backend/app/services/youtube/summary_job_handler.py`
- Modify: `backend/app/main.py`
- Modify: `backend/app/services/investment/x_web.py`
- Test: `backend/tests/test_model_runtime.py`, `backend/tests/test_youtube_api.py`, `backend/tests/test_reading_companion_worker.py`

- [ ] **Step 1: Add failing integration tests for session propagation**

```python
def test_reading_worker_uses_resolver_for_its_database_session(db_session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[Session] = []
    monkeypatch.setattr("app.services.reading_companion_dependencies.build_llm_client", lambda session: seen.append(session) or MockStructuredOutputClient())
    build_reading_companion_service(db_session)
    assert seen == [db_session]
```

- [ ] **Step 2: Run the failing integration test**

Run: `cd backend && .venv/bin/python -m pytest tests/test_model_runtime.py::test_reading_worker_uses_resolver_for_its_database_session -v`
Expected: FAIL because a current workload still calls a settings-only factory.

- [ ] **Step 3: Thread the current session into each factory**

Do not create global singleton clients. Request handlers use their dependency-injected session; schedulers and task workers construct a fresh resolver inside their already-open session. Make YouTube summary, translation, ASR, visual OCR and investment page OCR resolve at operation start so their task uses one consistent route.

- [ ] **Step 4: Re-run affected integration suites**

Run: `cd backend && .venv/bin/python -m pytest tests/test_model_runtime.py tests/test_youtube_api.py tests/test_reading_companion_worker.py -v`
Expected: PASS without changing existing API behavior when no managed route is configured.

- [ ] **Step 5: Commit workload integration**

```bash
git add backend/app/api/v1/entities.py backend/app/api/v1/investment.py backend/app/api/v1/youtube.py \
  backend/app/services/task_worker_dependencies.py backend/app/services/reading_companion_dependencies.py \
  backend/app/services/youtube/summary_job_handler.py backend/app/main.py \
  backend/app/services/investment/x_web.py backend/tests/test_model_runtime.py
git commit -m "feat: route AI workloads through model management"
```

### Task 7: Build the Settings model-management UI

**Files:**
- Create: `frontend/src/types/modelManagement.ts`
- Create: `frontend/src/services/modelManagementApi.ts`
- Create: `frontend/src/pages/ModelManagementPage.tsx`
- Create: `frontend/src/pages/ModelManagementPage.test.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/pages/SettingsPage.tsx`

- [ ] **Step 1: Write failing UI tests**

```tsx
it("masks credentials and saves the LLM default route", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValueOnce(jsonResponse([{ id: "p1", name: "OpenAI", api_key_configured: true, api_key_hint: "sk-…1234" }])));
  render(<MemoryRouter initialEntries={["/settings/models"]}><App /></MemoryRouter>);
  expect(await screen.findByText("sk-…1234")).toBeInTheDocument();
  expect(screen.queryByText("sk-private-key")).not.toBeInTheDocument();
  await user.selectOptions(screen.getByLabelText("LLM 默认模型"), "m1");
  await user.click(screen.getByRole("button", { name: "保存默认路由" }));
  expect(await screen.findByText("默认路由已保存")).toBeInTheDocument();
});
```

- [ ] **Step 2: Run the failing UI test**

Run: `cd frontend && npm run test -- src/pages/ModelManagementPage.test.tsx`
Expected: FAIL because the page and API client do not exist.

- [ ] **Step 3: Implement page and typed API client**

Use Ant Design `Table`, `Modal`, `Form`, `Select`, `Tag`, `Alert` and `Popconfirm`. Provider form fields are name, protocol, base URL, timeout and password input. The test action submits only current form state to `/providers/test`; save uses the CRUD API. The model table provides create/edit/enable controls. The route card presents one select per capability, filtered to enabled matching models.

Add `/settings/models` route and a clear link/card from `/settings`; replace the obsolete “模型路由占位项” copy without disturbing the YouTube retry controls.

- [ ] **Step 4: Re-run UI test**

Run: `cd frontend && npm run test -- src/pages/ModelManagementPage.test.tsx`
Expected: PASS for rendered masks, connection-test result and route save flow.

- [ ] **Step 5: Commit model management UI**

```bash
git add frontend/src/types/modelManagement.ts frontend/src/services/modelManagementApi.ts \
  frontend/src/pages/ModelManagementPage.tsx frontend/src/pages/ModelManagementPage.test.tsx \
  frontend/src/App.tsx frontend/src/pages/SettingsPage.tsx
git commit -m "feat: add model management settings UI"
```

### Task 8: Document deployment configuration and perform full verification

**Files:**
- Modify: `.env.example`
- Modify: `README.md`

- [ ] **Step 1: Document the deployment-only encryption key**

Add `MODEL_ENCRYPTION_KEY=` with a comment showing `Fernet.generate_key().decode()` as the generation method. State that it must remain stable across restarts or stored keys cannot be decrypted, and that existing LLM/Embedding/ASR/OCR `.env` values remain fallback-only.

- [ ] **Step 2: Run targeted static and end-to-end checks**

Run: `cd backend && .venv/bin/mypy app/services/model_crypto.py app/services/model_management.py app/services/model_connection_test.py app/services/model_runtime.py`
Expected: PASS.

Run: `cd backend && .venv/bin/python -m pytest tests/test_model_management.py tests/test_model_connection_test.py tests/test_model_runtime.py tests/test_model_management_api.py -v`
Expected: PASS.

- [ ] **Step 3: Run full repository verification**

Run: `cd backend && .venv/bin/python -m pytest && .venv/bin/ruff check .`
Expected: all backend tests pass and Ruff reports no violations.

Run: `cd frontend && npm run test && npm run lint && npm run build`
Expected: frontend tests, lint and production build all exit 0.

- [ ] **Step 4: Inspect the final diff for secrets and migration correctness**

Run: `git diff codex/feat-reading-companion...HEAD && git status --short`
Expected: no API Key values, no `.env` file, no generated dependency directories, and only intended source/docs changes.

- [ ] **Step 5: Commit documentation**

```bash
git add .env.example README.md
git commit -m "docs: document managed model deployment"
```
