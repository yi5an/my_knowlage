# Testing Guide

This guide defines the baseline checks every KnowPilot change should pass before review.

## Backend

Run from `backend/`:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
alembic upgrade head
ruff check .
mypy app
pytest
```

The default test path is `backend/tests`. Database tests use SQLite in memory unless a test explicitly opts into PostgreSQL.

For the provenance backend, run the focused contract suite before the complete gate:

```bash
pytest tests/test_provenance_schemas.py \
  tests/test_provenance_models.py \
  tests/test_provenance_evidence.py \
  tests/test_provenance_links.py \
  tests/test_provenance_domain.py \
  tests/test_provenance_query.py \
  tests/test_provenance_projection.py \
  tests/test_provenance_api.py \
  tests/test_provenance_rebuild_job.py -q
ruff check app/services/provenance app/api/v1/provenance.py tests/test_provenance_*.py
mypy app/services/provenance app/api/v1/provenance.py
```

Rebuild tests assert active-job deduplication, workspace isolation, partial-failure reporting, graph projection, and preservation of human-reviewed edges. The graph store is a disposable projection; assertions about durable provenance state must use the relational models.

The historical SQLite migration chain contains an older foreign-key alteration that SQLite cannot execute. To validate a new provenance migration locally, stamp a disposable database at its direct parent and run upgrade/downgrade for the new revision; validate the complete chain against PostgreSQL in CI.

## Frontend

Run from `frontend/`:

```bash
npm install
npm run lint
npm run test
npm run build
```

Frontend unit tests use Vitest with jsdom.

The provenance page additionally uses real Chromium WebGL checks:

```bash
npm run test:e2e -- e2e/provenance-3d.spec.ts
```

The deterministic 100/500/2000-node fixtures do not require a running backend. Browser assertions compare copied Three.js renderer, camera, control-target, selection, and resource counters. They cover left-drag rotation; Shift-left/middle/right pan; cursor wheel zoom; node and edge raycasting; empty-space double-click reset; arrow/plus/minus/R/Escape keyboard controls; reduced motion; no-WebGL fallback; unmount cleanup; and selected-path preservation at the low-quality 2000-node tier.

When visually reviewing the feature, check desktop and narrow viewports. Labels must not cover the audit drawer, path selection must remain legible, and status must remain distinguishable through text, glyphs, and line style—not color alone.

## Fixtures

Shared test fixtures live under root `tests/fixtures/`:

- `documents/`: markdown and plain text document samples.
- `entities/`: stock and industry-chain extraction samples.
- `research/`: RAG question/answer fixture with evidence and confidence.

Fixtures must not contain secrets, private documents, production customer data, or real API keys.

## CI Expectations

GitHub Actions runs backend and frontend jobs independently. A PR is ready for review only when:

- backend migration check passes;
- backend lint, type check, and tests pass;
- frontend lint, tests, and build pass;
- new modules include focused tests or documented test gaps.
