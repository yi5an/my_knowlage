# Event–Conclusion Provenance Data and API Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the schema-first PostgreSQL source of truth, provenance services, review history, query APIs, graph projection, and asynchronous rebuild job for the three-layer provenance graph.

**Architecture:** Keep immutable evidence anchors, versioned conclusions and trace edges in PostgreSQL; register every displayed object through stable `TraceNode` identities; project the same graph into the existing `GraphStore`; fall back to bounded PostgreSQL traversal when the graph store fails. FastAPI routes only validate workspace-scoped requests and call services.

**Tech Stack:** Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2.x, Alembic, PostgreSQL/SQLite-compatible tests, pytest, existing `TaskJob` and `GraphStore` abstractions.

---

## Scope and dependency boundary

This plan implements the backend contract consumed by the 3D frontend. It does not add WebGL components or new LLM prompts. The AI/history adapter work in `2026-09-03-provenance-ai-integration.md` starts after Tasks 1–5 here expose stable schemas and service APIs.

The canonical design is `docs/superpowers/specs/2026-09-03-event-conclusion-provenance-3d-design.md`.

## Task 1: Define provenance schemas before service logic

**Files:**

- Create: `backend/app/schemas/provenance.py`
- Create: `backend/tests/test_provenance_schemas.py`

- [x] Write failing tests for each locator type, invalid ranges, graph enums, and the “AI edge requires evidence” invariant.

```python
from pydantic import ValidationError

from app.schemas.provenance import (
    ConclusionLinkOutput,
    MediaSegmentLocator,
    PdfRegionLocator,
    TextSpanLocator,
)


def test_text_span_rejects_reversed_offsets() -> None:
    with pytest.raises(ValidationError):
        TextSpanLocator(chunk_id="chunk-1", start_offset=8, end_offset=4)


def test_pdf_region_rejects_bbox_outside_normalized_space() -> None:
    with pytest.raises(ValidationError):
        PdfRegionLocator(page_no=1, bbox=(0.1, 0.2, 1.2, 0.8))


def test_ai_link_requires_evidence_anchor_ids() -> None:
    with pytest.raises(ValidationError):
        ConclusionLinkOutput(
            source_backing_type="knowledge_event",
            source_backing_id="event-1",
            target_conclusion_id="conclusion-1",
            relation_type="supports",
            rationale="The event supports the conclusion.",
            confidence=0.8,
            evidence_anchor_ids=[],
        )
```

- [x] Run the schema tests and verify the expected import failure.

Run: `cd backend && pytest tests/test_provenance_schemas.py -q`

Expected: FAIL because `app.schemas.provenance` does not exist.

- [x] Add string enums and a discriminated locator union.

```python
class TraceLayer(StrEnum):
    conclusion = "conclusion"
    event = "event"
    evidence = "evidence"


class TraceRelationType(StrEnum):
    supports = "supports"
    refutes = "refutes"
    qualifies = "qualifies"
    explains = "explains"
    causes = "causes"
    derived_from = "derived_from"
    aggregates = "aggregates"
    related_unconfirmed = "related_unconfirmed"


class TextSpanLocator(BaseModel):
    type: Literal["text_span"] = "text_span"
    chunk_id: str = Field(min_length=1)
    start_offset: int = Field(ge=0)
    end_offset: int = Field(gt=0)

    @model_validator(mode="after")
    def offsets_increase(self) -> Self:
        if self.end_offset <= self.start_offset:
            raise ValueError("end_offset must be greater than start_offset")
        return self


EvidenceLocator = Annotated[
    TextSpanLocator
    | PdfRegionLocator
    | MediaSegmentLocator
    | ImageRegionLocator
    | WebFragmentLocator,
    Field(discriminator="type"),
]
```

- [x] Add `EvidenceAnchorCreate/Response`, `KnowledgeEventCreate/Response`, `ConclusionCreate/Response`, `ProvenanceNode`, `ProvenanceEdge`, `ProvenanceGraphResponse`, `TraceEdgeReviewRequest/Response`, `ProvenanceRebuildRequest/Response`, `FactEventExtractionOutput`, and `ConclusionLinkOutput`.

- [x] Make all confidence values `0..1`, all list fields use factories, and `ProvenanceGraphResponse` expose `graph_version`, `degraded`, `degraded_reason`, counts, `has_more`, and an optional cursor.

- [x] Run: `cd backend && pytest tests/test_provenance_schemas.py -q`

Expected: PASS.

- [x] Commit: `git add backend/app/schemas/provenance.py backend/tests/test_provenance_schemas.py && git commit -m "feat: define provenance schemas"`

## Task 2: Add the PostgreSQL source-of-truth models and migration

**Files:**

- Modify: `backend/app/infrastructure/models.py`
- Create: `backend/alembic/versions/202609030001_provenance_core.py`
- Create: `backend/tests/test_provenance_models.py`

- [x] Write model tests using the existing in-memory SQLite fixture style. Cover unique node registration, same-workspace edge endpoints, immutable anchor behavior at service level, edge evidence uniqueness, conclusion supersession, and review history persistence.

```python
def test_trace_node_backing_identity_is_unique(session: Session) -> None:
    session.add_all([
        TraceNode(id="n1", workspace_id="ws", layer="event", node_type="fact",
                  backing_type="investment_fact", backing_id="f1", label="A"),
        TraceNode(id="n2", workspace_id="ws", layer="event", node_type="fact",
                  backing_type="investment_fact", backing_id="f1", label="B"),
    ])
    with pytest.raises(IntegrityError):
        session.commit()
```

- [x] Run: `cd backend && pytest tests/test_provenance_models.py -q`

Expected: FAIL because the models do not exist.

- [x] Add `EvidenceAnchor`, `KnowledgeEvent`, `Conclusion`, `TraceNode`, `TraceEdge`, `TraceEdgeEvidence`, and `TraceEdgeReview` SQLAlchemy models. Use string primary keys, `JsonType`, explicit indexes, foreign keys, and named constraints consistent with `models.py`.

```python
class TraceNode(UpdatedTimestampMixin, Base):
    __tablename__ = "trace_node"
    __table_args__ = (
        UniqueConstraint(
            "workspace_id", "backing_type", "backing_id",
            name="uq_trace_node_backing",
        ),
        Index("idx_trace_node_workspace_layer", "workspace_id", "layer"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspace.id"), nullable=False)
    layer: Mapped[str] = mapped_column(String(32), nullable=False)
    node_type: Mapped[str] = mapped_column(String(64), nullable=False)
    backing_type: Mapped[str] = mapped_column(String(64), nullable=False)
    backing_id: Mapped[str] = mapped_column(String(64), nullable=False)
    label: Mapped[str] = mapped_column(Text(), nullable=False)
    occurred_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    confidence: Mapped[float | None] = mapped_column(Float())
    display_status: Mapped[str] = mapped_column(String(32), nullable=False)
    properties: Mapped[JsonObject] = mapped_column("properties_json", JsonType, default=dict)
```

- [x] Store `locator_json` and `model_metadata` in portable `JsonType`; use composite unique constraints for `trace_edge_evidence(edge_id, evidence_anchor_id)` and a monotonic integer `version_no` on conclusions and edges.

- [x] Write migration upgrade and downgrade operations. Set `down_revision = "202607230002"`. Create tables in dependency order and drop them in exact reverse order.

- [x] Run migration verification against a temporary SQLite database and the model tests. The repository's older `202607150005` migration cannot run from zero on SQLite because it adds a foreign key outside batch mode, so execution stamped a disposable database at `202607230002` and verified this migration's upgrade and downgrade independently.

Run: `cd backend && alembic upgrade head && pytest tests/test_provenance_models.py -q`

Expected: PASS; Alembic reports revision `202609030001`.

- [x] Commit: `git add backend/app/infrastructure/models.py backend/alembic/versions/202609030001_provenance_core.py backend/tests/test_provenance_models.py && git commit -m "feat: add provenance persistence models"`

## Task 3: Implement immutable evidence anchors

**Files:**

- Create: `backend/app/services/provenance/__init__.py`
- Create: `backend/app/services/provenance/evidence.py`
- Create: `backend/tests/test_provenance_evidence.py`

- [ ] Write failing tests for exact quote validation, chunk workspace isolation, PDF/page and media bounds, idempotent creation, stale detection, and re-anchoring without modifying the original row.

```python
def test_text_anchor_must_match_chunk_content(session: Session) -> None:
    service = EvidenceAnchorService(session)
    with pytest.raises(AppError) as exc:
        service.create(
            workspace_id="ws",
            request=EvidenceAnchorCreate(
                document_id="doc",
                version_id="ver",
                anchor_type="text_span",
                locator={"type": "text_span", "chunk_id": "chunk", "start_offset": 0,
                         "end_offset": 5},
                quote="wrong",
                created_by_type="user",
            ),
        )
    assert exc.value.code == "evidence_anchor_mismatch"
```

- [ ] Run: `cd backend && pytest tests/test_provenance_evidence.py -q`

Expected: FAIL because the service is missing.

- [ ] Implement `EvidenceAnchorService.create`, `mark_stale_for_version`, and `reanchor`. Resolve the owning document from the referenced version/chunk instead of trusting request IDs.

- [ ] Generate deterministic anchor IDs from workspace, immutable source version, canonical locator JSON, and quote hash. Return the existing row for an exact replay.

```python
def _anchor_id(workspace_id: str, version_id: str, locator: EvidenceLocator, quote: str) -> str:
    payload = json.dumps(locator.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
    digest = sha256(f"{workspace_id}|{version_id}|{payload}|{sha256(quote.encode()).hexdigest()}".encode()).hexdigest()
    return f"evidence_{digest[:32]}"
```

- [ ] Reject mutation of locator/quote and create a new anchor with `supersedes_anchor_id` when re-anchoring.

- [ ] Run: `cd backend && pytest tests/test_provenance_evidence.py -q`

Expected: PASS.

- [ ] Commit: `git add backend/app/services/provenance backend/tests/test_provenance_evidence.py && git commit -m "feat: validate immutable evidence anchors"`

## Task 4: Register stable nodes and create versioned links

**Files:**

- Create: `backend/app/services/provenance/registry.py`
- Create: `backend/app/services/provenance/links.py`
- Create: `backend/tests/test_provenance_links.py`

- [ ] Write failing tests for deterministic node IDs, backing object existence, workspace isolation, allowed layer direction, required evidence on AI links, stable replay, superseding reviewed links, and review history.

```python
def test_ai_link_without_anchor_is_rejected(session: Session) -> None:
    with pytest.raises(AppError) as exc:
        TraceLinkService(session).create(
            workspace_id="ws",
            source_node_id="event-node",
            target_node_id="conclusion-node",
            relation_type="supports",
            origin_type="ai",
            confidence=0.9,
            rationale="Observed change supports the forecast.",
            evidence_anchor_ids=[],
        )
    assert exc.value.code == "trace_evidence_required"
```

- [ ] Run: `cd backend && pytest tests/test_provenance_links.py -q`

Expected: FAIL.

- [ ] Implement `TraceRegistrationService.register`. Use `uuid5` with a fixed application namespace and `workspace_id/backing_type/backing_id`; validate the backing object through a mapping of repository lookups.

- [ ] Implement `TraceLinkService.create` with the canonical direction `evidence -> event/fact/signal -> conclusion`. Permit same-layer `related_unconfirmed` only for event normalization candidates.

- [ ] Lock reviewed versions from overwrite. A changed inference creates a new `TraceEdge` with `version_no + 1` and `supersedes_id`; an exact replay returns the current edge.

- [ ] Implement `review(edge_id, workspace_id, action, expected_version, reviewer_id, note)` using an update guarded by `version_no`. Insert `TraceEdgeReview` in the same transaction and raise `trace_review_conflict` on zero updated rows.

- [ ] Run: `cd backend && pytest tests/test_provenance_links.py -q`

Expected: PASS.

- [ ] Commit: `git add backend/app/services/provenance/registry.py backend/app/services/provenance/links.py backend/tests/test_provenance_links.py && git commit -m "feat: add stable provenance nodes and links"`

## Task 5: Add event and conclusion domain services

**Files:**

- Create: `backend/app/services/provenance/events.py`
- Create: `backend/app/services/provenance/conclusions.py`
- Create: `backend/tests/test_provenance_domain.py`

- [ ] Write failing tests for event `canonical_key`, uncertain duplicate preservation, investment/research conclusion adapters, version increments, and atomic node registration.

- [ ] Run: `cd backend && pytest tests/test_provenance_domain.py -q`

Expected: FAIL.

- [ ] Implement deterministic event keys from normalized subject/action/object, event type, and bounded time bucket. Return candidate matches separately; never merge solely on embedding similarity.

```python
@dataclass(frozen=True)
class EventNormalizationResult:
    event: KnowledgeEvent
    merged: bool
    candidate_event_ids: tuple[str, ...]
```

- [ ] Implement `ConclusionService.create`, `revise`, `from_investment_claim`, `from_investment_thesis`, and `from_reading_insight`. Persist the generic conclusion and register its trace node in one transaction.

- [ ] Map existing status vocabularies explicitly in module-level dictionaries; reject unknown values instead of silently defaulting.

- [ ] Run: `cd backend && pytest tests/test_provenance_domain.py -q`

Expected: PASS.

- [ ] Commit: `git add backend/app/services/provenance/events.py backend/app/services/provenance/conclusions.py backend/tests/test_provenance_domain.py && git commit -m "feat: add provenance event and conclusion services"`

## Task 6: Query paths and graph-store projection with explicit degradation

**Files:**

- Create: `backend/app/services/provenance/query.py`
- Create: `backend/app/services/provenance/projection.py`
- Create: `backend/tests/test_provenance_query.py`
- Create: `backend/tests/test_provenance_projection.py`

- [ ] Write failing tests for filtered overview, complete downward/upward focused paths, workspace isolation, deterministic graph version, explicit truncation metadata, projection parity, and graph-store failure fallback.

- [ ] Run: `cd backend && pytest tests/test_provenance_query.py tests/test_provenance_projection.py -q`

Expected: FAIL.

- [ ] Implement `ProvenanceQueryService.overview` and `trace`. The PostgreSQL walker uses a visited set, validates workspace on every selected node/edge, and caps traversal by explicit `max_nodes`/cursor metadata.

```python
try:
    graph = self._from_graph_store(request)
except Exception as exc:  # adapter failure, not an empty graph
    logger.warning("provenance graph store unavailable", exc_info=exc)
    graph = self._from_postgres(request, max_hops=2)
    graph.degraded = True
    graph.degraded_reason = "graph_store_unavailable"
```

- [ ] Compute `graph_version` from the maximum updated timestamps and result filters, so the frontend can seed layout deterministically and cache safely.

- [ ] Implement `ProvenanceProjectionService.sync_workspace` using `GraphStore.upsert_node` and `upsert_edge`. Prefix projection IDs/types so they cannot collide with the entity graph; projection deletion/rebuild must never delete PostgreSQL source rows.

- [ ] Add parity assertions comparing projected and PostgreSQL focused-path node/edge identities.

- [ ] Run: `cd backend && pytest tests/test_provenance_query.py tests/test_provenance_projection.py -q`

Expected: PASS.

- [ ] Commit: `git add backend/app/services/provenance/query.py backend/app/services/provenance/projection.py backend/tests/test_provenance_query.py backend/tests/test_provenance_projection.py && git commit -m "feat: query and project provenance paths"`

## Task 7: Expose workspace-scoped provenance APIs

**Files:**

- Create: `backend/app/api/v1/provenance.py`
- Modify: `backend/app/api/v1/router.py`
- Create: `backend/app/services/provenance/dependencies.py`
- Modify: `docs/development/api-conventions.md`
- Modify: `docs/development/error-codes.md`
- Create: `backend/tests/test_provenance_api.py`

- [ ] Write failing API tests for `overview`, both trace directions, edge detail, review success, 409 optimistic-lock conflict, conclusion creation, invalid locator 422, missing workspace access, and degraded response fields.

- [ ] Run: `cd backend && pytest tests/test_provenance_api.py -q`

Expected: FAIL with 404 because the router is not registered.

- [ ] Add `APIRouter(prefix="/provenance", tags=["provenance"])`. Use the project’s existing session/graph-store dependencies and pass `workspace_id` into every service call.

```python
@router.get("/nodes/{node_id}/trace", response_model=ProvenanceGraphResponse)
def trace_node(
    node_id: str,
    workspace_id: str,
    direction: TraceDirection,
    service: Annotated[ProvenanceQueryService, Depends(get_provenance_query_service)],
) -> ProvenanceGraphResponse:
    return service.trace(workspace_id=workspace_id, node_id=node_id, direction=direction)
```

- [ ] Add error-code documentation for `evidence_anchor_mismatch`, `trace_evidence_required`, `trace_invalid_direction`, `trace_review_conflict`, `provenance_path_too_large`, and `provenance_object_not_found`.

- [ ] Register the router in `backend/app/api/v1/router.py` and document pagination/degradation conventions.

- [ ] Run: `cd backend && pytest tests/test_provenance_api.py -q`

Expected: PASS.

- [ ] Commit: `git add backend/app/api/v1/provenance.py backend/app/api/v1/router.py backend/app/services/provenance/dependencies.py docs/development/api-conventions.md docs/development/error-codes.md backend/tests/test_provenance_api.py && git commit -m "feat: expose provenance APIs"`

## Task 8: Run rebuilds through `task_job`

**Files:**

- Create: `backend/app/services/provenance/rebuild_job.py`
- Modify: `backend/app/main.py`
- Modify: `backend/app/api/v1/provenance.py`
- Create: `backend/tests/test_provenance_rebuild_job.py`

- [ ] Write failing tests that `POST /provenance/rebuild` creates one pending job, duplicate active requests reuse that job, the handler is registered, progress/output are persisted, partial item failures are reported, and reruns preserve reviewed edges.

- [ ] Run: `cd backend && pytest tests/test_provenance_rebuild_job.py -q`

Expected: FAIL.

- [ ] Add `PROVENANCE_REBUILD_JOB_TYPE = "provenance_rebuild"`, a handler implementing the existing `JobHandler` protocol, and an idempotent `register()` that assigns `_HANDLERS[PROVENANCE_REBUILD_JOB_TYPE]`.

- [ ] Make the first backend-only handler register existing objects and project already-persisted trace rows. The extraction/enrichment stages are added by the AI integration plan without changing the job contract.

```python
def register() -> None:
    from app.services.task_worker import _HANDLERS

    _HANDLERS[PROVENANCE_REBUILD_JOB_TYPE] = ProvenanceRebuildJobHandler()
```

- [ ] Register the handler in the `main.py` lifespan alongside the other job handlers.

- [ ] Implement `GET /provenance/jobs/{job_id}` by reusing the existing task-job response convention and enforcing workspace ownership.

- [ ] Run: `cd backend && pytest tests/test_provenance_rebuild_job.py -q`

Expected: PASS.

- [ ] Commit: `git add backend/app/services/provenance/rebuild_job.py backend/app/main.py backend/app/api/v1/provenance.py backend/tests/test_provenance_rebuild_job.py && git commit -m "feat: add provenance rebuild job"`

## Task 9: Backend regression and contract handoff

**Files:**

- Modify: `README.md`
- Modify: `docs/development/testing-guide.md`

- [ ] Document the provenance endpoints, rebuild workflow, PostgreSQL/graph-store ownership, and the exact backend verification commands.

- [ ] Run focused tests:

Run: `cd backend && pytest tests/test_provenance_schemas.py tests/test_provenance_models.py tests/test_provenance_evidence.py tests/test_provenance_links.py tests/test_provenance_domain.py tests/test_provenance_query.py tests/test_provenance_projection.py tests/test_provenance_api.py tests/test_provenance_rebuild_job.py -q`

Expected: PASS.

- [ ] Run the complete backend quality gate:

Run: `cd backend && ruff check . && mypy app && pytest`

Expected: all commands exit 0.

- [ ] Inspect migration state:

Run: `cd backend && alembic heads`

Expected: exactly one head, `202609030001`.

- [ ] Commit: `git add README.md docs/development/testing-guide.md && git commit -m "docs: document provenance backend"`

- [ ] Record the final commit SHA and API contract in the frontend plan handoff; do not begin frontend work against an uncommitted schema.

## Implementation completion criteria

- PostgreSQL retains immutable evidence, stable node identities, versioned edges/conclusions, and append-only review history.
- All writes and reads enforce workspace ownership.
- Both traversal directions return the same canonical edge direction.
- Missing graph storage returns an explicitly degraded, bounded PostgreSQL path.
- Rebuild is asynchronous and idempotent through `task_job`.
- Backend quality gates pass without excluding the new modules.
