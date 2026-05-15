# Backend Database Notes

## Alembic

Run migrations from the backend directory:

```bash
alembic upgrade head
```

The default local database is SQLite (`sqlite:///./knowpilot.db`). Development and production should use PostgreSQL through `DATABASE_URL`, for example:

```bash
DATABASE_URL=postgresql+psycopg://knowpilot:knowpilot@localhost:5432/knowpilot alembic upgrade head
```

## SQLite Compatibility

The ORM uses SQLAlchemy `JSON` with a PostgreSQL `JSONB` variant. PostgreSQL gets JSONB columns and GIN indexes for high-volume metadata/property queries. SQLite stores these fields as JSON text-compatible columns and skips PostgreSQL-only GIN indexes in the migration.

SQLite is intended for local tests and lightweight development only. Query behavior around JSON operators and indexing is not equivalent to PostgreSQL.

## Document Import

Agent 2 adds the first document import API surface:

- `POST /api/v1/documents/import/file`
- `POST /api/v1/documents/import/url`
- `GET /api/v1/documents`
- `GET /api/v1/documents/{doc_id}`
- `GET /api/v1/documents/{doc_id}/versions/{version_id}`
- `PUT /api/v1/documents/{doc_id}/content`

Uploaded files are stored through `LocalFileStorage`, which is intentionally isolated behind a small abstraction so a later MinIO-compatible backend can replace it. Parsed content is saved as `document_version` rows and split into `document_chunk` rows. Import attempts create `task_job` records, including failed parser jobs.

Initial parser support includes txt, markdown, csv, pdf, docx, and xlsx. Image OCR has an explicit parser interface and currently returns a clear not-implemented parse error.
