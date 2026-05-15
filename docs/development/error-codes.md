# Error Codes

KnowPilot errors use stable machine-readable codes in the `error.code` field.

| Code | HTTP Status | Meaning |
|---|---:|---|
| `http_error` | varies | Generic HTTP exception wrapper. |
| `validation_error` | 422 | Request payload, query, or path validation failed. |
| `not_found` | 404 | Requested resource does not exist or is outside the workspace. |
| `conflict` | 409 | Resource state conflicts with the requested operation. |
| `unauthorized` | 401 | Authentication is missing or invalid. |
| `forbidden` | 403 | Caller lacks permission for the resource. |
| `internal_error` | 500 | Unexpected server error. |

Future feature Agents should add domain-specific codes here when they introduce new failure modes.

Error responses must not include secrets, raw provider credentials, or full internal stack traces.

