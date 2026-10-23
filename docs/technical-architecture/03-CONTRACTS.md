# 03 — REST contracts and immutable schemas

Implementation checkpoint, 20 October 2026: test snapshots, paginated history, restore, contract validation, encrypted connections for five providers and immutable agent publication now exist. The actual API shapes are exported in `backend/openapi.json`. Configuration schema v1 includes `provider` and `model_id`; a published version pins the verified connection and credential generation. The richer capability envelope below remains a future schema migration for execution needs. Publication validates local schemas and a narrow OpenAI GPT-5 Mini output profile, but never calls a model. Example checks validate shape only, never model quality.

All examples are proposed contracts, not executable implementation. UUID placeholders in prose are illustrative. JSON Schema blocks describe the structural contract; semantic rules follow them. Pydantic request/response models will generate OpenAPI and the TypeScript DTOs. Hand-maintain only form-specific Zod validation and pure frontend state, not a second complete API model.

## Common API rules

Base `/api/v1`; JSON UTF-8; secure cookie session and CSRF for browser mutations; workspace ID in URL plus server ownership checks. Dates: UTC ISO8601. Decimal money: strings in requests/responses. Unknown request fields rejected. Output artifacts accessed separately, never included in every list row.

List query: `limit=25` (1–100), opaque cursor, `q` max 100 characters, allowlisted sort/filter fields. Stable key `(created_at,id)` descending for run history. Response `{items: [...], next_cursor: null}`; do not require an expensive total count.

Structured error: `{error:{code,message,details:[{path,node_id,edge_id,message}],request_id}}`. No stack traces or credentials. 401 unauthenticated; 403 recognized resource but action forbidden; 404 missing/out-of-workspace resource; 409 revision/idempotency conflict; 422 structural/semantic request invalid; 429 rate/quota/concurrency limit with Retry-After where known; 503 dependency unavailable. Return safe public errors with the same envelope for framework validation failures.

Mutation response statuses: create=201; durable queued command=202; read/save=200; revoke/logout=204. Long execution is never inside a request. Saves include `expected_revision`; response includes current revision. Schema version is independent of API version and user-visible version number.

`Idempotency-Key` required for run/retry submission and supported for version publication. Scope to workspace+actor+operation; hash key and canonical request body. Concurrent duplicates resolve through a database unique constraint and return the stored response. Different body with same key →409. Proposed retention 24h; after expiry the key may create a new command, so it is not an unlimited deduplication promise. Definition/tool side-effect deduplication is separate and longer lived.

## Identity and workspace endpoints

| Endpoint | Request → response | Authority |
|---|---|---|
| GET /auth/csrf | none → token; create/refresh pre-auth context if needed | Browser origin checks |
| POST /auth/register | email,password →201 safe user + session cookie | Rate-limited, pre-auth CSRF |
| POST /auth/login | email,password →200 safe user + session cookie | Generic credentials error, pre-auth CSRF |
| GET /auth/session | none →user, memberships, csrf token | Valid session |
| POST /auth/logout | none →204; revoke current session | Session+CSRF |
| POST /auth/logout-all | password reauthentication →204; revoke all sessions | Session+CSRF |
| POST /auth/password | current_password,new_password →204; rotate current session and revoke others | Session+CSRF |
| GET /workspaces | cursor →memberships | Session |
| POST /workspaces | name →201 workspace + owner membership | Session |
| GET /workspaces/{w} | none →metadata, own role, effective limits | Member |
| PATCH /workspaces/{w} | name,expected_revision →metadata | Admin/owner |
| PATCH /workspaces/{w}/limits | expected_revision,lowered limits/concurrency →effective policy | Owner; cannot raise platform ceilings |
| GET /workspaces/{w}/members | cursor →member summaries | Admin/owner |
| POST /workspaces/{w}/members | existing user email,role →membership | Owner/admin within role limits |
| PATCH /workspaces/{w}/members/{m} | role →membership | Owner/admin within role limits |
| DELETE /workspaces/{w}/members/{m} | none →204 | Protect final owner |

MVP membership is adding an already registered user, not pretending email invitations are delivered. Login/register/session responses use `Cache-Control: no-store`. Recovery/reset/email verification are separate launch-readiness slices when a mail service is selected; no dead “forgot password” affordance.

## Definitions and registry endpoints

All following are under `/workspaces/{w}`.

| Endpoint | Request → response |
|---|---|
| GET /agents | q,status,cursor →AgentSummary[] |
| POST /agents | name,description,config →AgentDraft |
| GET /agents/{a} | →AgentDraft and latest published version metadata |
| PATCH /agents/{a} | expected_revision,name,description,config →AgentDraft |
| POST /agents/{a}/duplicate | name →new draft with independent ID |
| POST /agents/{a}/archive | expected_revision →archived summary |
| POST /agents/{a}/test-snapshots | expected_revision →201 immutable AgentVersion(purpose=test) |
| POST /agents/{a}/versions | expected_revision,change_summary →201 AgentVersion(purpose=published) |
| GET /agents/{a}/versions | purpose filter,cursor →version summaries |
| GET /agents/{a}/versions/{versionId} | →immutable AgentVersion |
| POST /agents/{a}/restore | version_id,expected_revision →new draft revision |
| GET /models | →server capability registry for configured provider, availability and pricing revision |
| GET /tools | q,effect_class,cursor →ToolSummary[] |
| POST /tools | installed_handler_key,name,policy →ToolDefinition + first version |
| GET /tools/{t} | →safe definition and immutable version metadata |
| GET /tools/{t}/versions/{versionId} | →immutable schemas, scopes and safe execution policy |
| POST /tools/{t}/versions | expected_revision,policy/schema from installed handler →ToolVersion |
| POST /tools/{t}/revoke | reason →revocation metadata |
| GET /workflows | q,status,cursor →WorkflowSummary[] |
| POST /workflows | name,description,graph →WorkflowDraft |
| GET /workflows/{f} | →WorkflowDraft and latest published metadata |
| PATCH /workflows/{f} | expected_revision,name,description,graph →WorkflowDraft |
| POST /workflows/{f}/duplicate | name →independent draft |
| POST /workflows/{f}/archive | expected_revision →archived summary |
| POST /workflows/{f}/validate | expected_revision →ValidationResult |
| POST /workflows/{f}/versions | expected_revision,execution_hash,change_summary →201 published WorkflowVersion |
| GET /workflows/{f}/versions | cursor →version summaries |
| GET /workflows/{f}/versions/{versionId} | →immutable graph |
| POST /workflows/{f}/restore | version_id,expected_revision →new draft revision |

Editors/owners/admins manage definitions; viewers read redacted summaries. Tool registration/version/revoke requires admin/owner and an installed allowlisted handler; API registration does not upload executable code or arbitrary network destinations. Model registry is safe metadata, not credentials or hard-coded frontend model claims.

Draft graph saves may contain incomplete connections for ongoing editing, but must pass structural bounds. Test snapshot/publication requires complete semantic validation. Validate returns `{revision,execution_hash,validator_version,valid,errors,warnings}`; errors include actionable codes/JSON paths. Publication always rechecks current permissions, graph, source revision and supplied hash; a prior browser validation result is not authority.

## Runs, monitoring, usage and connections

| Endpoint under /workspaces/{w} | Request → response |
|---|---|
| POST /runs | RunCreate →202 RunAccepted |
| GET /runs | state,kind,definition_id,from,to,cursor →redacted RunSummary[] |
| GET /runs/{r} | →RunDetail with current state/steps/budgets/error metadata |
| GET /runs/{r}/steps/{s} | →step/attempts/call metadata and authorized artifact links |
| GET /runs/{r}/events | after_sequence(default 0),limit(max 100) →events,last_sequence,has_more |
| POST /runs/{r}/cancel | reason optional →202 cancellation request or 200 existing terminal outcome |
| POST /runs/{r}/retry | limits optional →202 new linked run; original input/version retained |
| GET /artifacts/{id} | →bounded authorized JSON/text with no-store headers |
| GET /usage | from,to →counts,tokens,settled/reserved/uncertain costs,quota periods |
| GET /integrations | →supported configured connection summaries only |
| POST /integrations | provider_key,display_name,credential →201 masked connection metadata |
| POST /integrations/{id}/rotate | credential →new active credential generation metadata |
| DELETE /integrations/{id} | →204 revoke; prevents new calls, does not erase audit |
| GET /audit | target,action,cursor →sanitized audit records (admin/owner) |

Saving a connection validates credential format and encryption, not live connectivity. Connection UI says “Credentials saved · not yet verified” until an actual bounded provider run supplies evidence; revoked/invalid credentials surface safe diagnostics. A separate background connection-check product/contract is deferred. Health routes `/health/live` and `/health/ready` are infrastructure endpoints outside the versioned business API; detailed diagnostics/metrics are internal only.

RunCreate:

```json
{
  "definition": {"kind": "agent", "version_id": "11111111-1111-4111-8111-111111111111"},
  "input": {"ticket": "My order arrived damaged."},
  "limits": {"timeout_seconds": 60, "max_cost_usd": "0.10000000"}
}
```

`definition.kind` is agent/workflow, version must belong to workspace and be executable. Test agent snapshots are allowed for direct tests only; workflows require published agent versions. Effective limits are the minimum of request, definition, provider capability and workspace/platform policy. A caller cannot raise a cap. RunAccepted: `{id,state:"queued",definition,events_url,correlation_id}`. Poll returns only persisted state; state changes are not inferred from elapsed time. Retry is a full new run, not in-place rewind, and refuses any history with uncertain/non-replay-safe side effects until a future operator-resolution policy exists.

## Agent configuration JSON Schema

Draft form may be incomplete in UI local state. A stored config must be structurally valid; snapshot creation additionally validates live registry references. Server-owned envelope fields are not writable configuration.

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "urn:flowforge:agent-config:1",
  "type": "object",
  "additionalProperties": false,
  "required": ["schema_version", "instructions", "model", "input_schema", "output_schema", "tools", "limits", "retry"],
  "properties": {
    "schema_version": {"const": 1},
    "instructions": {"type": "string", "minLength": 1, "maxLength": 32000},
    "model": {
      "type": "object", "additionalProperties": false,
      "required": ["connection_id", "model_id", "max_output_tokens"],
      "properties": {
        "connection_id": {"type": "string", "format": "uuid"},
        "model_id": {"type": "string", "minLength": 1, "maxLength": 200},
        "max_output_tokens": {"type": "integer", "minimum": 1, "maximum": 16384},
        "temperature": {"type": "number", "minimum": 0, "maximum": 2}
      }
    },
    "input_schema": {"type": "object"},
    "output_schema": {"type": "object"},
    "tools": {
      "type": "array", "maxItems": 16,
      "items": {
        "type": "object", "additionalProperties": false,
        "required": ["alias", "tool_version_id", "scopes", "destination_ids"],
        "properties": {
          "alias": {"type": "string", "pattern": "^[a-z][a-z0-9_]{0,63}$"},
          "tool_version_id": {"type": "string", "format": "uuid"},
          "scopes": {"type": "array", "maxItems": 16, "uniqueItems": true, "items": {"type": "string", "minLength": 1, "maxLength": 100}},
          "destination_ids": {"type": "array", "maxItems": 16, "uniqueItems": true, "items": {"type": "string", "format": "uuid"}}
        }
      }
    },
    "limits": {
      "type": "object", "additionalProperties": false,
      "required": ["max_iterations", "timeout_seconds", "max_cost_usd", "max_tool_calls"],
      "properties": {
        "max_iterations": {"type": "integer", "minimum": 1, "maximum": 20},
        "timeout_seconds": {"type": "integer", "minimum": 1, "maximum": 300},
        "max_cost_usd": {"type": "string", "pattern": "^(0|[1-9][0-9]{0,3})(\\.[0-9]{1,8})?$"},
        "max_tool_calls": {"type": "integer", "minimum": 0, "maximum": 32}
      }
    },
    "retry": {
      "type": "object", "additionalProperties": false,
      "required": ["max_attempts", "base_delay_seconds"],
      "properties": {
        "max_attempts": {"type": "integer", "minimum": 1, "maximum": 3},
        "base_delay_seconds": {"type": "integer", "minimum": 1, "maximum": 10}
      }
    }
  }
}
```

Schema bounds are platform ceilings; defaults proposal: 8 model iterations, 60 seconds, $0.10 and 8 tool calls, 3 total attempts for safe failures. `max_iterations` counts all dispatched model calls, including potentially billable failed attempts. `max_attempts` includes the first attempt, not “first plus N retries”. No silent defaults inside immutable snapshots: materialize them at creation.

Semantic validation checks unique aliases, tool capability/scopes/destinations, model support for tools/structured output/temperature/token caps and credential availability. Zero monetary cap is permitted only for a deterministic no-cost test/local path. Do not invent a generic provider parameter superset; omit unsupported optional parameters.

AgentVersion response envelope:

| Field | Meaning |
|---|---|
| id,workspace_id,agent_id,number | Server-generated immutable identity; number increases across test and published snapshots |
| purpose | test or published; immutable |
| schema_version,source_revision | Interpretation version and draft revision snapshotted |
| config,config_hash | Validated effective definition and canonical semantic hash |
| capability_snapshot,handler_revisions | What the selected model and tool handlers supported at creation |
| created_by,created_at,change_summary | Provenance |

Model aliases may change behind a provider; pin an explicit model revision when available and report the limitation when it is not. Versioning gives configuration reproducibility, not deterministic LLM output. Credential values are intentionally not copied into versions; current connection rotation/revocation applies at runtime. Record actual model/pricing/credential-generation identifiers on calls without secret values.

Immutable agent-version envelope schema (the schema registry resolves the config URN to the AgentConfig schema above; it performs no network fetch):

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "urn:flowforge:agent-version:1",
  "type": "object", "additionalProperties": false,
  "required": ["id", "workspace_id", "agent_id", "number", "purpose", "schema_version", "source_revision", "config", "config_hash", "capability_snapshot", "handler_revisions", "created_by", "created_at", "change_summary"],
  "properties": {
    "id": {"type": "string", "format": "uuid"},
    "workspace_id": {"type": "string", "format": "uuid"},
    "agent_id": {"type": "string", "format": "uuid"},
    "number": {"type": "integer", "minimum": 1},
    "purpose": {"enum": ["test", "published"]},
    "schema_version": {"const": 1},
    "source_revision": {"type": "integer", "minimum": 1},
    "config": {"$ref": "urn:flowforge:agent-config:1"},
    "config_hash": {"type": "string", "pattern": "^[a-f0-9]{64}$"},
    "capability_snapshot": {
      "type": "object", "additionalProperties": false,
      "required": ["provider_key", "model_id", "structured_output", "tool_calling", "max_input_tokens", "max_output_tokens", "registry_revision"],
      "properties": {
        "provider_key": {"type": "string", "minLength": 1},
        "model_id": {"type": "string", "minLength": 1},
        "structured_output": {"type": "boolean"},
        "tool_calling": {"type": "boolean"},
        "max_input_tokens": {"type": "integer", "minimum": 1},
        "max_output_tokens": {"type": "integer", "minimum": 1},
        "registry_revision": {"type": "string", "minLength": 1}
      }
    },
    "handler_revisions": {"type": "object", "maxProperties": 16, "additionalProperties": {"type": "string", "minLength": 1}},
    "created_by": {"type": "string", "format": "uuid"},
    "created_at": {"type": "string", "format": "date-time"},
    "change_summary": {"type": "string", "maxLength": 1000}
  }
}
```

The server computes SHA-256 over canonical JSON semantic configuration (materialized defaults, stable object keys and normalized numeric policy). Schema validation alone cannot make a record immutable; database privileges/triggers and publish-only service paths enforce that separately. Model capability/pricing snapshots report known provider metadata, not invented quality scores.

## Supported user JSON Schema subset

Input/output schemas use a constrained JSON Schema 2020-12 subset: object, array, string, integer, number, boolean, null; properties/required/additionalProperties; enum/const; bounded items/length/ranges. No remote `$ref`, dynamic references, custom executable validators, unbounded recursion or user regex in MVP. Max depth 8, schema size 64KiB, serialized input/output 256KiB. Enforce format checks explicitly; a `format` keyword alone is not proof of validation. The platform schema may use regex/oneOf internally; restrictions apply to user-supplied schemas. [JSON Schema core specification](https://json-schema.org/draft/2020-12/json-schema-core).

## Workflow graph JSON Schema

Nodes form a discriminated union by `type`. Edges name ports and carry field mappings; conditions select a `true` or `false` output port. A mapping is either a literal JSON value or an upstream field selected by JSON Pointer. No expression interpolation, eval, arbitrary functions or embedded code.

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "urn:flowforge:workflow-graph:1",
  "type": "object", "additionalProperties": false,
  "required": ["schema_version", "nodes", "edges", "input_schema", "output_schema", "limits"],
  "properties": {
    "schema_version": {"const": 1},
    "nodes": {"type": "array", "minItems": 1, "maxItems": 100, "items": {"$ref": "#/$defs/node"}},
    "edges": {"type": "array", "maxItems": 200, "items": {"$ref": "#/$defs/edge"}},
    "input_schema": {"type": "object"},
    "output_schema": {"type": "object"},
    "limits": {
      "type": "object", "additionalProperties": false,
      "required": ["timeout_seconds", "max_cost_usd", "max_parallel_steps"],
      "properties": {
        "timeout_seconds": {"type": "integer", "minimum": 1, "maximum": 300},
        "max_cost_usd": {"type": "string", "pattern": "^(0|[1-9][0-9]{0,3})(\\.[0-9]{1,8})?$"},
        "max_parallel_steps": {"type": "integer", "minimum": 1, "maximum": 4}
      }
    }
  },
  "$defs": {
    "nodeId": {"type": "string", "pattern": "^[a-z][a-z0-9_-]{0,63}$"},
    "binding": {
      "oneOf": [
        {"type": "object", "additionalProperties": false, "required": ["kind", "value"], "properties": {"kind": {"const": "literal"}, "value": {}}},
        {"type": "object", "additionalProperties": false, "required": ["kind", "node_id", "pointer"], "properties": {"kind": {"const": "output"}, "node_id": {"$ref": "#/$defs/nodeId"}, "pointer": {"type": "string", "maxLength": 512, "pattern": "^(/.*)?$"}}}
      ]
    },
    "node": {
      "type": "object", "additionalProperties": false,
      "required": ["id", "type", "label", "position", "join", "policy", "config"],
      "properties": {
        "id": {"$ref": "#/$defs/nodeId"},
        "type": {"enum": ["manual_input", "agent", "tool", "condition", "transform", "result"]},
        "label": {"type": "string", "minLength": 1, "maxLength": 100},
        "position": {"type": "object", "additionalProperties": false, "required": ["x", "y"], "properties": {"x": {"type": "number", "minimum": -100000, "maximum": 100000}, "y": {"type": "number", "minimum": -100000, "maximum": 100000}}},
        "join": {"enum": ["all", "active"]},
        "policy": {
          "type": "object", "additionalProperties": false,
          "required": ["timeout_seconds", "max_attempts"],
          "properties": {"timeout_seconds": {"type": "integer", "minimum": 1, "maximum": 300}, "max_attempts": {"type": "integer", "minimum": 1, "maximum": 3}}
        },
        "config": {"type": "object"}
      },
      "oneOf": [
        {"properties": {"type": {"const": "manual_input"}, "config": {"type": "object", "additionalProperties": false}}},
        {"properties": {"type": {"const": "agent"}, "config": {"type": "object", "additionalProperties": false, "required": ["agent_version_id"], "properties": {"agent_version_id": {"type": "string", "format": "uuid"}}}}},
        {"properties": {"type": {"const": "tool"}, "config": {"type": "object", "additionalProperties": false, "required": ["tool_version_id", "scopes", "destination_ids"], "properties": {"tool_version_id": {"type": "string", "format": "uuid"}, "scopes": {"type": "array", "maxItems": 16, "uniqueItems": true, "items": {"type": "string", "minLength": 1, "maxLength": 100}}, "destination_ids": {"type": "array", "maxItems": 16, "uniqueItems": true, "items": {"type": "string", "format": "uuid"}}}}}},
        {"properties": {"type": {"const": "condition"}, "config": {"type": "object", "additionalProperties": false, "required": ["operator", "left", "right"], "properties": {"operator": {"enum": ["eq", "ne", "gt", "gte", "lt", "lte"]}, "left": {"$ref": "#/$defs/binding"}, "right": {"$ref": "#/$defs/binding"}}}}},
        {"properties": {"type": {"const": "transform"}, "config": {"type": "object", "additionalProperties": false, "required": ["fields", "output_schema"], "properties": {"fields": {"type": "object", "minProperties": 1, "maxProperties": 64, "propertyNames": {"pattern": "^[a-zA-Z][a-zA-Z0-9_]{0,63}$"}, "additionalProperties": {"$ref": "#/$defs/binding"}}, "output_schema": {"type": "object"}}}}},
        {"properties": {"type": {"const": "result"}, "config": {"type": "object", "additionalProperties": false, "required": ["value"], "properties": {"value": {"$ref": "#/$defs/binding"}}}}}
      ]
    },
    "edge": {
      "type": "object", "additionalProperties": false,
      "required": ["id", "source", "source_port", "target", "target_port", "mappings"],
      "properties": {
        "id": {"$ref": "#/$defs/nodeId"},
        "source": {"$ref": "#/$defs/nodeId"},
        "source_port": {"enum": ["out", "true", "false"]},
        "target": {"$ref": "#/$defs/nodeId"},
        "target_port": {"const": "in"},
        "mappings": {
          "type": "array", "maxItems": 64,
          "items": {
            "type": "object", "additionalProperties": false, "required": ["from", "to"],
            "properties": {"from": {"type": "string", "maxLength": 512, "pattern": "^(/.*)?$"}, "to": {"type": "string", "maxLength": 512, "pattern": "^(/.*)?$"}}
          }
        }
      }
    }
  }
}
```

Structural examples of typed configurations:

| Node | Config | Input/output |
|---|---|---|
| manual_input | `{}` | Output is graph input_schema; no incoming edge |
| agent | `{agent_version_id}` | Pinned version input_schema → output_schema |
| tool | `{tool_version_id,scopes,destination_ids}` | Pinned handler input_schema → output_schema |
| condition | `{operator:"eq",left:{kind:"output",node_id:"triage",pointer:"/priority"},right:{kind:"literal",value:"urgent"}}` | Emits same resolved input on exactly one true/false port |
| transform | `{fields:{priority:{kind:"output",node_id:"triage",pointer:"/priority"}},output_schema:{...}}` | Builds a bounded flat object from literal/upstream fields |
| result | `{value:{kind:"output",node_id:"format",pointer:""}}` | Value must satisfy graph output_schema |

Schemas for manual/agent/tool/result ports are derived, not duplicate editable fields. Transform supplies its validated declared output schema. Condition output matches its resolved input; input assembled by edge mappings. Invalid/unknown inferred compatibility blocks publication; runtime validates actual values too.

Graph semantics:

- Exactly one manual_input and exactly one terminal result for MVP; every node reachable from input and able to reach result. Max graph serialized size 512KiB; node/edge caps as above.
- Node and edge IDs unique; no duplicate endpoint+port edges; no self edges/cycles; valid source/target ports. Condition has exactly one true and one false outgoing edge; other nodes use out; result has none. Input has no incoming edge.
- A node with multiple parents uses explicit join `all` or `active`. `active` waits for every incoming edge to resolve and requires at least one activated edge; it does not race the fastest predecessor. `all` requires every incoming edge activated; otherwise skip. See execution document for full behavior.
- Mapping `from` is a JSON Pointer into edge source output; `to` is a JSON Pointer into target input. Empty pointer maps the entire value. Decode `~0`/`~1` per JSON Pointer, disallow malformed escapes, prototype-sensitive keys, depth/size overflow and conflicting target writes on concurrently active edges. JSON objects are data, never JS object mutation instructions.
- Bindings in condition/transform/result may only reference an upstream node with a dependency path. Required referenced values must be present on every feasible activation path. Optional branch fields need explicit union/null handling in the supported subset; do not guess or coerce types.
- `all` joins downstream of mutually exclusive branches are rejected as unreachable; use active join. Graph validator uses conservative branch/path analysis bounded by graph size and rejects unsupported ambiguous mappings rather than proving arbitrary schemas equivalent.
- Node policy cannot loosen pinned agent/tool or run policy. Workflow and agent attempt caps do not multiply: effective node attempts = minimum of node, agent/tool and server caps. Provider SDK auto-retries disabled.

## Workflow publication and compatibility

Draft retains graph layout and revision. Publication revalidates, derives FK projections, allocates immutable version number, snapshots graph+validator version and writes audit in one transaction. `execution_hash` excludes position/label/viewport and includes type/config/ports/mappings/schema/limits. A separate saved revision still changes for layout edits. Backend compares exact draft revision during publish, even if semantic hash is unchanged.

No `latest` dependency resolution during execution. Restoring creates a new draft; editing an agent does not alter existing workflows. Tool revocation and model availability can prevent historical versions from running for security/operational reasons. Unsupported schema versions fail with `SCHEMA_VERSION_UNSUPPORTED`; explicit migration produces a new draft/version and never silently mutates history.
