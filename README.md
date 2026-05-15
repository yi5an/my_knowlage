# KnowPilot

KnowPilot is a local-first AI knowledge base. This repository currently contains the project bootstrap, database model layer, CI checks, fixtures, and development documentation needed for parallel Agent work.

## Prerequisites

- Python 3.12
- Node.js 20+
- Docker and Docker Compose

## Backend

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
alembic upgrade head
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Health check:

```bash
curl http://localhost:8000/api/v1/health
```

Expected response:

```json
{"status":"ok"}
```

Backend checks:

```bash
cd backend
alembic upgrade head
pytest
ruff check .
mypy app
```

## Frontend

```bash
cd frontend
npm install
npm run dev
```

Frontend checks:

```bash
cd frontend
npm run lint
npm run test
npm run build
```

## Docker Compose

```bash
cp .env.example .env
docker compose -f docker-compose.dev.yml up --build
```

Services:

- Backend: http://localhost:8000
- Frontend: http://localhost:5173
- PostgreSQL: localhost:5432
- Redis: localhost:6379

## Current Scope

This repository intentionally does not yet implement document import, AI provider calls, RAG, graph synchronization, or research workflows. Those belong to later Agent tasks.

## Development Docs

- [Local development guide](docs/development/local-dev-guide.md)
- [Testing guide](docs/development/testing-guide.md)
- [API conventions](docs/development/api-conventions.md)
- [Error codes](docs/development/error-codes.md)
