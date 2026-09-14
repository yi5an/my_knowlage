# Local Development Guide

## Prerequisites

- Python 3.12
- Node.js 20+
- Docker and Docker Compose

## Environment

Create a local environment file:

```bash
cp .env.example .env
```

Do not commit `.env` or secrets.

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

## Frontend

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173`.

## Docker Compose

```bash
docker compose -f docker-compose.dev.yml up --build
```

Services:

- Backend: `http://localhost:8000`
- Frontend: `http://localhost:5173`
- PostgreSQL: `localhost:5432`
- Redis: `localhost:6379`

## Investment opportunity operations

The investment opportunity loop is workspace-scoped and evidence-first. Run both
backfills from `backend/`; each prints one JSON object with `created`,
`skipped`, `failed`, `seen`, and `failure_reasons`. Re-running the same command
is idempotent for pending/running/succeeded jobs and already-promoted signals.

```bash
cd backend
python -m scripts.backfill_person_impact --workspace-id ws_default \
  --limit 500 --as-of 2026-09-15T00:00:00+00:00 --dry-run
python -m scripts.backfill_opportunity_candidates --workspace-id ws_default \
  --limit 500 --dry-run
```

Remove `--dry-run` only after inspecting the counters. Both commands support
`--workspace-id`, `--limit`, `--dry-run`, and `--as-of`; an offset-naive
`--as-of` is interpreted as UTC. The person backfill requires a real
`InvestmentPersonSource` plus one explicit `symbol`/`ticker` in a
`human_source` or `expert_opinion` item. It deliberately does not infer an
account from prose or a ticker from a theme/watchlist. The opportunity
backfill copies only an explicit candidate payload from signal feedback and
never fabricates `catalyst`, `risk_flags`, or `invalidation_conditions`.

### Providers, quality, and visible failures

The default market provider is Stooq (`MARKET_DATA_PROVIDER=stooq`,
`MARKET_DATA_BASE_URL=https://stooq.com`) in the exchange timezone
`America/New_York`. Daily bars can arrive after the market close. Event
snapshots retain provider name, URL/query range, exchange timezone, missing
dates, and whether adjusted close was raw. Quality is reported as `complete`,
`partial`, `missing`, `stale`, or `invalid`. Operators should expect explicit
messages such as `market provider error` (timeout/rate limit), `market bars
missing`, `未能确定唯一标的`, and `搜索服务未配置`; do not silently promote a
row when one of these is present.

The asynchronous worker job type is `person_impact_refresh`. Opportunity
promotion is the gate-protected backfill command (not an external follow API).
Calibration is performed by `OutcomeService.recalculate_recommendation_weights`
and only includes outcomes with `observed_at <= as_of`; fewer than ten
evaluated outcomes returns `样本不足` without changing weights.

To pause a recommendation, mark its status `dismissed`/`paused` through the
service/API. This preserves source snapshots, events, and outcomes for audit;
do not delete the recommendation or evidence.

### Migration rollback and as-of rebuild

For a controlled rollback of the opportunity discovery schema:

```bash
cd backend
alembic upgrade 202609140002
alembic downgrade 202609030002  # rolls back 202609140002 and 202609140001
alembic upgrade 202609140002    # restore after verification
```

Take a database backup first and verify pre-existing investment rows before
and after the cycle. To rebuild a historical person profile, run
`backfill_person_impact` with the same workspace and `--as-of`, then let the
`person_impact_refresh` jobs finish; the input cutoff is retained for audit.
Create a new digest snapshot from the same as-of database view with
`InvestmentService.create_digest_snapshot`. Snapshots are append-only, so
historical digests remain available and are never overwritten.
