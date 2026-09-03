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
