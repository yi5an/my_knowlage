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
| `evidence_anchor_mismatch` | 400 | Quote or locator does not match persisted source content. |
| `evidence_anchor_unchanged` | 400 | Re-anchoring produced the same immutable anchor. |
| `trace_evidence_required` | 400 | An AI-generated link has no valid evidence anchor. |
| `trace_invalid_direction` | 400 | A link violates the canonical layer direction. |
| `trace_review_action_invalid` | 400 | The requested review action is unknown. |
| `trace_review_conflict` | 409 | The edge changed after the client loaded its version. |
| `provenance_path_too_large` | 400 | Focused path requires explicit pagination or aggregation. |
| `provenance_object_not_found` | 404 | Provenance object does not exist in the requested workspace. |
| `provenance_status_unknown` | 400 | A legacy status cannot be mapped without guessing. |

Future feature Agents should add domain-specific codes here when they introduce new failure modes.

Error responses must not include secrets, raw provider credentials, or full internal stack traces.
