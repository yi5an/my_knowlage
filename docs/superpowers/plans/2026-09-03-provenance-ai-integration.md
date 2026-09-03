# Event–Conclusion Provenance AI and Historical Integration Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Connect existing reading, investment, YouTube, macro, and research outputs to the provenance source of truth; make fact/signal reruns identity-stable; and generate evidence-bound event/conclusion relations through structured model output.

**Architecture:** Adapt persisted source objects into immutable `EvidenceAnchor`, `TraceNode`, and `Conclusion` records instead of duplicating retrieval. Extend AI schemas with resolvable evidence references, reject unsupported relationships at the service boundary, preserve human review during idempotent reruns, and run historical backfill through the existing provenance rebuild job.

**Tech Stack:** Python 3.12, Pydantic v2 structured output, SQLAlchemy 2.x, Alembic, existing model-provider abstraction, `ReadingEvidenceAdapter`, `TaskJob`, pytest.

---

## Scope and dependency boundary

Begin after Tasks 1–5 and 8 of `2026-09-03-provenance-data-api.md` are merged. This plan may extend those services but must not change the public API response shape without updating both the backend and frontend contract tests. It does not implement WebGL rendering.

The canonical design is `docs/superpowers/specs/2026-09-03-event-conclusion-provenance-3d-design.md`.

## Task 1: Add stable domain keys without deleting historical rows

**Files:**

- Modify: `backend/app/infrastructure/models.py`
- Create: `backend/alembic/versions/202609030002_provenance_domain_keys.py`
- Modify: `backend/tests/test_provenance_models.py`

- [ ] Add failing model tests for nullable legacy rows, unique active fact/signal keys inside one workspace, inactive superseded rows, and allowed reuse across workspaces.

```python
def test_active_fact_key_is_unique_per_workspace(session: Session) -> None:
    session.add_all([
        make_fact(id="f1", canonical_key="same", is_active=True),
        make_fact(id="f2", canonical_key="same", is_active=True),
    ])
    with pytest.raises(IntegrityError):
        session.commit()
```

- [ ] Run: `cd backend && pytest tests/test_provenance_models.py -q`

Expected: FAIL because the domain key columns are missing.

- [ ] Add `canonical_key`, `is_active`, and `supersedes_id` to `InvestmentFact` and `InvestmentSignal`. Keep `canonical_key` nullable for pre-backfill rows; new service writes must always populate it.

- [ ] In PostgreSQL, create partial unique indexes for active non-null keys. In SQLite-compatible model tests, enforce the same behavior with an appropriate filtered index or service check.

- [ ] Write migration `down_revision = "202609030001"`. Add columns first, backfill only deterministic non-null keys, then create indexes. Downgrade drops indexes before columns.

- [ ] Run: `cd backend && alembic upgrade head && pytest tests/test_provenance_models.py -q`

Expected: PASS and one Alembic head `202609030002`.

- [ ] Commit: `git add backend/app/infrastructure/models.py backend/alembic/versions/202609030002_provenance_domain_keys.py backend/tests/test_provenance_models.py && git commit -m "feat: add stable provenance domain keys"`

## Task 2: Convert persisted reading evidence into provenance records

**Files:**

- Create: `backend/app/services/provenance/adapters.py`
- Modify: `backend/app/services/reading_evidence.py`
- Create: `backend/tests/test_provenance_adapters.py`
- Modify: `backend/tests/test_reading_evidence.py`

- [ ] Write failing tests for these mappings:

  - `DocumentChunk` plus offsets to `text_span`
  - a chunk with page metadata to `pdf_region` when a normalized bbox exists
  - YouTube transcript metadata to `media_segment`
  - `VideoFrameAnalysis` region/OCR metadata to `image_region`
  - `ReadingInsight` to `Conclusion(research)` plus its primary anchor
  - `ReadingCorroboration.supports/contradicts/contextualizes` to `supports/refutes/qualifies`
  - wrong-workspace source rejection

- [ ] Run: `cd backend && pytest tests/test_provenance_adapters.py tests/test_reading_evidence.py -q`

Expected: FAIL.

- [ ] Extend `ReadingEvidenceCandidate` with optional immutable locator material while keeping current callers source-compatible.

```python
@dataclass(frozen=True)
class ReadingEvidenceCandidate:
    source_kind: str
    source_id: str
    workspace_id: str
    document_id: str | None
    version_id: str | None
    chunk_id: str | None
    locator: EvidenceLocator | None
    title: str
    excerpt: str
    published_at: datetime | None
    retrieval_score: float
```

- [ ] Make `ReadingEvidenceAdapter` remain the retrieval aggregator. Add locator data only from persisted fields; do not infer a page, timestamp, or bbox that is absent.

- [ ] Implement `ProvenanceAdapter.from_candidate`, `from_reading_insight`, and `from_reading_corroboration`. If a candidate lacks a resolvable locator, return an explicit `unanchored` result and do not create a supported edge.

- [ ] Preserve the insight’s existing user review: `confirmed -> confirmed`, `dismissed -> rejected`, and `active -> ai_generated/pending_review`. Preserve `evidence_state` separately as validation status.

- [ ] Run: `cd backend && pytest tests/test_provenance_adapters.py tests/test_reading_evidence.py -q`

Expected: PASS.

- [ ] Commit: `git add backend/app/services/provenance/adapters.py backend/app/services/reading_evidence.py backend/tests/test_provenance_adapters.py backend/tests/test_reading_evidence.py && git commit -m "feat: adapt reading evidence to provenance"`

## Task 3: Make investment fact extraction locator-bound and identity-stable

**Files:**

- Modify: `backend/app/services/investment/fact_extraction.py`
- Modify: `backend/tests/test_investment_fact_extraction.py`

- [ ] Replace the current weak idempotency expectation with failing assertions that identical reruns preserve fact ID, trace-node ID, anchor ID, and reviewed links; changed facts create a new version/inactive predecessor without deleting history.

- [ ] Add failing tests that an excerpt must resolve inside persisted source content or a captured web fragment; a timestamp must produce a media anchor; a frame reference must produce an image anchor; and fabricated evidence is skipped with an item-level failure count.

- [ ] Run: `cd backend && pytest tests/test_investment_fact_extraction.py -q`

Expected: FAIL because the service deletes facts and assigns random UUIDs.

- [ ] Replace the local extraction item schema with the shared evidence-reference contract from `app.schemas.provenance`.

```python
class InvestmentFactExtractionItem(BaseModel):
    fact_text: str = Field(min_length=1)
    fact_text_zh: str | None = None
    fact_type: str = "other"
    entities: list[str] = Field(default_factory=list)
    evidence: EvidenceReference
    confidence: float = Field(ge=0, le=1)
```

- [ ] Include numbered, bounded source segments in the prompt. The model returns a source segment ID plus quote/offset within that segment; application code translates it to an `EvidenceLocator` and verifies the exact excerpt.

- [ ] Compute `canonical_key = sha256(source_item_id + evidence_anchor_id + normalized_fact_text)`. Upsert by workspace/key, update mutable presentation fields, and mark disappeared prior AI facts inactive. Never issue bulk `delete(InvestmentFact)`.

- [ ] In the same transaction, create/reuse the anchor, upsert the fact, register its middle-layer node, and create the `derived_from` edge. Roll back that fact only when its anchor cannot validate; continue other facts and report `facts_skipped` with reason counts.

- [ ] Run: `cd backend && pytest tests/test_investment_fact_extraction.py -q`

Expected: PASS.

- [ ] Commit: `git add backend/app/services/investment/fact_extraction.py backend/tests/test_investment_fact_extraction.py && git commit -m "refactor: preserve evidence-backed fact identity"`

## Task 4: Make signal refresh stable and provenance-aware

**Files:**

- Modify: `backend/app/services/investment/signal_service.py`
- Modify: `backend/tests/test_investment_signals.py`

- [ ] Strengthen `test_refresh_signals_is_idempotent_for_same_fact_cluster` so it asserts `second[0].id == first[0].id`, the same trace-node ID remains, and prior review state is unchanged.

- [ ] Add failing tests for cluster membership changes, inactive superseded signals, stable input ordering, one `aggregates` edge per active member fact, and removal of stale aggregation edges without touching reviewed edges.

- [ ] Run: `cd backend && pytest tests/test_investment_signals.py -q`

Expected: FAIL because refresh deletes and recreates signals.

- [ ] Compute a stable cluster key from workspace, watchlist, signal type, normalized primary entity, and sorted member fact canonical keys. Sort input facts before clustering.

```python
def _signal_key(workspace_id: str, group: _SignalGroup) -> str:
    members = "|".join(sorted(fact.canonical_key or fact.id for fact in group.facts))
    raw = f"{workspace_id}|{group.watchlist_id or ''}|{group.signal_type}|{group.entity}|{members}"
    return sha256(raw.encode()).hexdigest()
```

- [ ] Upsert active matching signals, mark vanished AI signals inactive/superseded, and retain IDs for exact reruns. Register each signal node and upsert `fact -> signal` aggregation edges.

- [ ] Keep `first_seen_at` monotonic minimum, update `last_seen_at`, and do not reset validation/review fields on refresh.

- [ ] Run: `cd backend && pytest tests/test_investment_signals.py -q`

Expected: PASS.

- [ ] Commit: `git add backend/app/services/investment/signal_service.py backend/tests/test_investment_signals.py && git commit -m "refactor: preserve investment signal identity"`

## Task 5: Persist research claims with resolvable evidence references

**Files:**

- Modify: `backend/app/schemas/research.py`
- Modify: `backend/app/services/research_agent.py`
- Modify: `backend/app/services/research_prompts.py`
- Modify: `backend/tests/test_research_agent.py`

- [ ] Write failing schema/workflow tests that every generated claim references stored `ResearchSource` identities, local excerpts resolve to document chunks, web excerpts retain captured URL/time/text, unsupported claims persist only as `unverified`, and an identical research rerun reuses conclusion/anchor identities.

- [ ] Run: `cd backend && pytest tests/test_research_agent.py -q`

Expected: FAIL because `ResearchClaim.evidence` is free-form text and claims are only transitively stored in report metadata.

- [ ] Add a structured reference and keep report presentation text derived from it.

```python
class ResearchEvidenceReference(BaseModel):
    source_id: str = Field(min_length=1)
    quote: str = Field(min_length=1)
    stance: Literal["supports", "refutes", "qualifies"] = "supports"


class ResearchClaim(BaseModel):
    text: str = Field(min_length=1)
    evidence_refs: list[ResearchEvidenceReference] = Field(default_factory=list)
    confidence: float = Field(ge=0, le=1)
```

- [ ] Give persisted `ResearchSource` rows deterministic IDs/keys and return those IDs to workflow state. Update prompts to enumerate sources by ID and require evidence references to use only those IDs.

- [ ] For local document sources, resolve the quote to a concrete version/chunk and exact character range. For web sources, create a `web_fragment` anchor from the persisted captured snippet, URL snapshot, and capture time. Do not turn a title or URL alone into evidence.

- [ ] Persist each research claim through `ConclusionService`; create evidence-to-event/fact and event/fact-to-conclusion links only when anchors validate. A claim with no valid reference remains visible as `unverified/insufficient_evidence` with no fabricated supporting edge.

- [ ] Retain the current safe fallback after structured-output failure, but fallback claims must be unverified until their source snippet is resolved and anchored.

- [ ] Run: `cd backend && pytest tests/test_research_agent.py -q`

Expected: PASS.

- [ ] Commit: `git add backend/app/schemas/research.py backend/app/services/research_agent.py backend/app/services/research_prompts.py backend/tests/test_research_agent.py && git commit -m "feat: persist evidence-bound research conclusions"`

## Task 6: Upgrade investment claim verification to edge-level evidence

**Files:**

- Modify: `backend/app/services/investment/claim_verifier.py`
- Modify: `backend/tests/test_investment_claim_verifier.py`
- Create: `backend/tests/test_investment_provenance_integration.py`

- [ ] Write failing tests for local `ReadingEvidenceAdapter` reuse, structured `supports/refutes/qualifies` verdicts, exact anchor linkage, no-evidence behavior, web failure, claim/conclusion adapter reuse, and preservation of existing claim fields.

- [ ] Run: `cd backend && pytest tests/test_investment_claim_verifier.py tests/test_investment_provenance_integration.py -q`

Expected: FAIL because verification stores only document IDs and a summary.

- [ ] Add a Pydantic `ClaimVerificationOutput` whose judgments reference candidate IDs and include stance, rationale, and confidence. Pass only retrieved candidates to the model.

- [ ] Use `ReadingEvidenceAdapter` for persisted candidates. Persist a web result as a captured `web_fragment` before it becomes a candidate; if only a URL/title is available, record it as an unanchored source and do not call it supporting evidence.

- [ ] Adapt `InvestmentClaim` to `Conclusion(investment)`, register evidence/event/conclusion nodes, and create one versioned edge per verdict with `TraceEdgeEvidence` rows. Map mixed support/refutation to `validation_status="conflicted"`.

- [ ] Continue updating legacy `verification_status`, `verification_summary`, and `evidence_doc_ids` for current UI compatibility, in the same transaction as provenance writes.

- [ ] Run: `cd backend && pytest tests/test_investment_claim_verifier.py tests/test_investment_provenance_integration.py -q`

Expected: PASS.

- [ ] Commit: `git add backend/app/services/investment/claim_verifier.py backend/tests/test_investment_claim_verifier.py backend/tests/test_investment_provenance_integration.py && git commit -m "feat: link investment claims to exact evidence"`

## Task 7: Extract and normalize events with structured output

**Files:**

- Create: `backend/app/services/provenance/extraction.py`
- Create: `backend/app/services/provenance/prompts.py`
- Create: `backend/tests/test_provenance_extraction.py`

- [ ] Write failing tests for JSON-schema validation, evidence-reference resolution, event canonicalization, ambiguous duplicate candidates, invalid model references, provider metadata, partial batch failure, and idempotent rerun.

- [ ] Run: `cd backend && pytest tests/test_provenance_extraction.py -q`

Expected: FAIL.

- [ ] Implement `ProvenanceExtractionService` with the existing `StructuredOutputClient`; never instantiate or name a provider in this module.

- [ ] Prompt with numbered anchors and require `FactEventExtractionOutput`. Validate that every returned reference belongs to the current workspace/input batch before creating `KnowledgeEvent` or links.

- [ ] Use `EventNormalizationService` to combine entity IDs, action, object IDs, time window, and semantic score. On ambiguity, retain separate events and add `related_unconfirmed`; do not create `causes` solely from similarity.

- [ ] Save model identifier, prompt version, generated time, and schema version in `model_metadata`, excluding keys and raw credentials.

- [ ] Run: `cd backend && pytest tests/test_provenance_extraction.py -q`

Expected: PASS.

- [ ] Commit: `git add backend/app/services/provenance/extraction.py backend/app/services/provenance/prompts.py backend/tests/test_provenance_extraction.py && git commit -m "feat: extract evidence-bound provenance events"`

## Task 8: Generate conclusion relations and preserve uncertainty

**Files:**

- Create: `backend/app/services/provenance/conclusion_linker.py`
- Create: `backend/tests/test_provenance_conclusion_linker.py`
- Modify: `backend/app/core/config.py`
- Modify: `backend/app/services/investment/source_trace_service.py`
- Modify: `backend/tests/test_source_trace_service.py`

- [ ] Write failing tests for supports/refutes/qualifies/explains mappings, the higher `causes` threshold, required anchor IDs, conflict aggregation, unchanged reviewed edges, and source-trace mappings remaining unconfirmed.

- [ ] Run: `cd backend && pytest tests/test_provenance_conclusion_linker.py tests/test_source_trace_service.py -q`

Expected: FAIL.

- [ ] Implement `ConclusionLinker` with shared `ConclusionLinkOutput`. Validate endpoints and evidence in `TraceLinkService`; the linker must not bypass service invariants with direct ORM inserts.

- [ ] Require `causes` to pass configured minimum confidence plus at least two independent source anchors, or remain `explains/related_unconfirmed`. Make thresholds configuration values, not provider-specific constants.

- [ ] Aggregate edge verdicts into conclusion `validation_status`: only support yields `supported`; only refutation yields `refuted`; both yield `conflicted`; no confirmed evidence yields `insufficient_evidence` or `unverified`.

- [ ] Map `InvestmentSourceTrace` types to `related_unconfirmed` by default. Promote only after exact anchors and an explicit verifier/human review establish the stronger relation.

- [ ] Run: `cd backend && pytest tests/test_provenance_conclusion_linker.py tests/test_source_trace_service.py -q`

Expected: PASS.

- [ ] Commit: `git add backend/app/services/provenance/conclusion_linker.py backend/tests/test_provenance_conclusion_linker.py backend/app/core/config.py backend/app/services/investment/source_trace_service.py backend/tests/test_source_trace_service.py && git commit -m "feat: link conclusions with evidence-aware verdicts"`

## Task 9: Extend the rebuild job into an idempotent staged pipeline

**Files:**

- Modify: `backend/app/services/provenance/rebuild_job.py`
- Create: `backend/app/services/provenance/backfill.py`
- Create: `backend/scripts/backfill_provenance.py`
- Modify: `backend/tests/test_provenance_rebuild_job.py`
- Create: `backend/tests/test_provenance_backfill.py`

- [ ] Write failing tests for ordered stages, progress checkpoints, workspace scoping, restart from a failed stage, per-record error capture, reviewed-edge preservation, stable IDs across two full runs, and a dry-run that writes nothing.

- [ ] Run: `cd backend && pytest tests/test_provenance_rebuild_job.py tests/test_provenance_backfill.py -q`

Expected: FAIL.

- [ ] Implement stages in this order: anchor existing evidence, adapt existing conclusions/facts/signals/events, extract missing events, link conclusions, recompute validation status, project graph. Store the last completed stage and counts in `TaskJob.output`.

- [ ] Commit each stage’s successful records independently while recording per-record failures; a total stage failure marks the job failed and retains the last checkpoint. Resuming must skip exact completed keys.

- [ ] Add a CLI with explicit workspace and dry-run flags:

Run: `cd backend && python scripts/backfill_provenance.py --workspace-id ws_default --dry-run`

Expected: prints counts by backing type and writes zero provenance rows.

- [ ] Require `--workspace-id`; do not allow an implicit all-workspace mutation. A real run creates a `TaskJob` rather than running LLM work synchronously in the CLI.

- [ ] Run the same populated fixture twice and assert equal active IDs/counts and unchanged review history.

- [ ] Run: `cd backend && pytest tests/test_provenance_rebuild_job.py tests/test_provenance_backfill.py -q`

Expected: PASS.

- [ ] Commit: `git add backend/app/services/provenance/rebuild_job.py backend/app/services/provenance/backfill.py backend/scripts/backfill_provenance.py backend/tests/test_provenance_rebuild_job.py backend/tests/test_provenance_backfill.py && git commit -m "feat: backfill provenance graph safely"`

## Task 10: End-to-end evidence audit and regression

**Files:**

- Create: `backend/tests/test_provenance_pipeline_integration.py`
- Modify: `README.md`
- Modify: `docs/development/testing-guide.md`

- [ ] Build one deterministic integration fixture containing a document paragraph, PDF locator metadata, YouTube transcript/frame, reading insight/corroboration, investment fact/signal/claim, macro event, and research claim.

- [ ] Test both directions end to end: conclusion down to exact anchors and event/fact/signal up to every affected conclusion. Assert canonical stored edge direction in both responses.

- [ ] Test statuses `confirmed`, `ai_generated`, `pending_review`, `rejected`, `supported`, `refuted`, `conflicted`, `insufficient_evidence`, and `stale`, including human review surviving a rebuild.

- [ ] Test a broken graph-store adapter and verify a bounded response with `degraded=true` rather than an empty successful graph.

- [ ] Run focused integration:

Run: `cd backend && pytest tests/test_provenance_pipeline_integration.py -q`

Expected: PASS.

- [ ] Run complete backend gates:

Run: `cd backend && ruff check . && mypy app && pytest`

Expected: all commands exit 0.

- [ ] Document the source adapters, evidence resolution rules, backfill dry-run, explicit workspace requirement, partial-failure semantics, and how to inspect/retry a rebuild job.

- [ ] Commit: `git add backend/tests/test_provenance_pipeline_integration.py README.md docs/development/testing-guide.md && git commit -m "test: verify provenance pipeline end to end"`

## Implementation completion criteria

- Existing reading, investment, macro, YouTube, and research records appear through stable provenance identities.
- Exact paragraph/page/region/time/frame/web-snapshot anchors are validated before supporting relationships are written.
- Fact and signal reruns never use delete-and-recreate and preserve reviewed history.
- LLM output is structured, provider-independent, evidence-bound, and explicitly uncertain when it cannot be anchored.
- `ReadingEvidenceAdapter` remains the retrieval source; provenance adapters add immutability and audit semantics.
- Historical backfill is workspace-scoped, asynchronous for real runs, resumable, dry-runnable, and idempotent.
- Full backend quality gates pass.
