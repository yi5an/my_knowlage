# API Conventions

## Versioning

All public API routes use the `/api/v1` prefix. Breaking API changes require a new version prefix.

## Response Shape

Successful object responses should return JSON objects with typed fields defined by Pydantic schemas. Collection endpoints should include pagination metadata once collection APIs are implemented.

Health check response:

```json
{"status":"ok"}
```

## Error Shape

Errors use the backend `ErrorResponse` structure:

```json
{
  "error": {
    "code": "validation_error",
    "message": "Request validation failed.",
    "details": []
  }
}
```

## Identifiers

Database identifiers use string IDs with table-specific prefixes where useful, for example `ws_`, `doc_`, `ent_`, and `job_`.

## AI Output Requirements

AI-generated API results must include:

- evidence references;
- confidence values;
- model/provider metadata when model calls are involved.

Do not hardcode provider names or API keys in request handlers.

## Provenance Graph

Event–conclusion provenance uses `/api/v1/provenance`. Stored edges always point from
evidence toward events/facts/signals and then toward conclusions; `direction=down`
and `direction=up` control traversal without reversing that stored direction.

Overview and trace responses include `graph_version`, node counts, `has_more`, and
an optional `next_cursor`. If the graph-store projection is unavailable, the API
returns a bounded PostgreSQL result with `degraded=true` and a non-empty
`degraded_reason` rather than presenting it as a complete graph.

Edge review requests include the current `version_no`. A stale review is rejected
with HTTP 409 so clients can refetch without overwriting another review.
