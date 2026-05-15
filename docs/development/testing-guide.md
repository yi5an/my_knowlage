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

