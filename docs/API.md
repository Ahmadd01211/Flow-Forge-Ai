# API contract proposal

Initial sketch, superseded by the [final contracts and schemas](technical-architecture/03-CONTRACTS.md).

Base `/api/v1`; JSON; authenticated secure HttpOnly session cookie. Unsafe methods require CSRF protection and allowed Origin. All workspace routes verify membership and resource ownership server-side. UUID identifiers; UTC ISO 8601 timestamps; USD decimals encoded as strings. Generated OpenAPI becomes the implementation contract.

| Method and route | Contract |
|---|---|
| POST /auth/register | email/password → 201 user + session; generic conflict response |
| POST /auth/login | credentials → session; rate-limited |
| GET /auth/session | user and membership summary, or 401 |
| POST /auth/logout | revoke session → 204 |
| GET, POST /workspaces | list memberships / create workspace |
| GET, PATCH /workspaces/{w} | inspect / update metadata (admin/owner) |
| GET, POST /workspaces/{w}/members | list / add existing user by approved membership flow |
| PATCH, DELETE /workspaces/{w}/members/{m} | change role / remove, protect last owner |
| GET, POST /workspaces/{w}/agents | paginated list / create draft |
| GET, PATCH /workspaces/{w}/agents/{a} | inspect / save draft with expected_revision |
| POST /workspaces/{w}/agents/{a}/duplicate | new independent draft |
| POST /workspaces/{w}/agents/{a}/archive | preserve versions and history |
| GET, POST /workspaces/{w}/agents/{a}/versions | list / validate and publish immutable version |
| GET /workspaces/{w}/agents/{a}/versions/{v} | inspect pinned definition |
| GET, POST /workspaces/{w}/tools | list / register approved definition (admin/owner) |
| GET /workspaces/{w}/tools/{t} | schemas, scopes and safe policy metadata |
| GET, POST /workspaces/{w}/workflows | list / create draft |
| GET, PATCH /workspaces/{w}/workflows/{f} | read / save graph with expected_revision |
| POST /workspaces/{w}/workflows/{f}/validate | expected_revision → graph hash, errors, warnings |
| GET, POST /workspaces/{w}/workflows/{f}/versions | list / publish after fresh server validation |
| GET /workspaces/{w}/workflows/{f}/versions/{v} | immutable graph |
| POST /workspaces/{w}/runs | pinned definition + input + limits; Idempotency-Key → 202 |
| GET /workspaces/{w}/runs | cursor list, state/definition/date filters |
| GET /workspaces/{w}/runs/{r} | state, steps, budgets, sanitized output/error |
| GET /workspaces/{w}/runs/{r}/events | after_sequence, limit; reconnect-safe events |
| POST /workspaces/{w}/runs/{r}/cancel | request cancellation → 202, terminal → current result |
| POST /workspaces/{w}/runs/{r}/retry | new linked run; reauthorize and validate budgets → 202 |
| GET /workspaces/{w}/artifacts/{id} | authorized bounded download; no public guessed URLs |
| GET /workspaces/{w}/integrations | actual supported connections only |
| POST /workspaces/{w}/integrations/provider | admin/owner stores credential server-side; returns masked metadata |
| DELETE /workspaces/{w}/integrations/{id} | revoke connection; audit and prevent further use |
| GET /workspaces/{w}/usage | date range, costs/tokens/limits; estimates labeled |
| GET /workspaces/{w}/audit | paginated owner/admin audit feed |
| GET /health/live, /health/ready | process / dependency readiness without credentials |

## Core payloads

```json
{
  "definition": {"kind": "workflow", "version_id": "uuid"},
  "input": {"ticket": "My order arrived damaged"},
  "limits": {"timeout_seconds": 60, "max_cost_usd": "0.10"}
}
```

Run response: `{ "id": "uuid", "state": "queued", "events_url": "...", "correlation_id": "uuid" }`. Validate input against version schema; reject increased limits beyond server policy. Idempotency key scoped to workspace/actor/route with body hash; same key plus different body yields 409.

Graph draft: `{ expected_revision, nodes: [{ id, type, position, config, input_schema, output_schema, execution_policy }], edges: [{ id, source, target, source_port, target_port, mapping, branch }] }`. Enforce payload/node/edge/schema depth limits.

Validation: `{ revision, graph_hash, valid, errors: [{ code, node_id, edge_id, path, message, remediation }], warnings: [] }`. Agent version IDs and tool permissions are validated in the same workspace.

Errors: `{ "error": { "code": "MAPPING_REQUIRED", "message": "Map ticket before publishing.", "details": [{"node_id":"triage","path":"input.ticket"}], "request_id":"uuid" } }`. Statuses: 400 malformed, 401 unauthenticated, 403 forbidden action, 404 missing/out-of-scope resource, 409 revision/idempotency conflict, 422 validation, 429 quota/rate limit, 503 dependency unavailable.

List response: `{ items: [], next_cursor: null }`; limit default 25, maximum 100. Poll event stream initially; SSE is optional when justified and must use the same authorization, event sequence and redaction. Reconnect never invents intermediate states.
