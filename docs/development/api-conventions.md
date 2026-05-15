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

