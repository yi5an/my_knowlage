#!/bin/sh
# Production entrypoint for the backend container.
# Runs migrations (idempotent) then starts uvicorn. The app's lifespan starts
# the YouTube polling scheduler and the async task_job worker automatically.
set -e

mkdir -p /app/storage

echo "[start_prod] applying alembic migrations..."
alembic upgrade head

echo "[start_prod] starting uvicorn on :8010..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8010
