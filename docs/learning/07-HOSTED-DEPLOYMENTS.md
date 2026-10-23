# Hosted deployments: using FlowForge from another app

Published OpenAI GPT-5 Mini, Gemini 2.5 Flash, DeepSeek Flash/V4 Pro, Claude Haiku 4.5, and OpenRouter GPT-4o-mini agents can execute through deployments when the workspace has a verified, active key for the pinned provider and model. DeepSeek uses its Responses API with structured JSON output. FlowForge validates the result against the published schema and records token usage. Its cost budget is an estimate, not a billing guarantee. OpenRouter routes GPT-4o-mini only to upstreams that accept the structured-output parameters. Other verified models can be configured and published, but cannot yet execute.

An owner or admin opens **Deployments**, chooses a published agent or workflow version, names the endpoint, and creates a key. The key appears once. FlowForge stores only its SHA-256 hash and a short visible prefix. Put the full key in the calling application's server-side secret store, never in browser code. Rotate it to invalidate the old key, or revoke the deployment to stop access and request cancellation of its active runs.

A deployment pins exactly one immutable version. A caller cannot choose another version or grant more tools in a request. The existing run service checks the published version, current provider credential and tool approvals when accepting an agent run. Workflow submissions check the current local-tool approvals. Each run records its deployment ID, so a key can poll only the runs it created. The database keeps encrypted inputs and outputs; Celery still receives only run IDs.

The external API is asynchronous. Set a new `Idempotency-Key` for each logical request, and reuse it when retrying the same request. The response contains a run ID and state. Poll that run until it completes, fails or is cancelled. An unchanged key with a different input returns 409. A deployment has a Redis-backed limit of 60 submissions and 240 status reads per minute; the API fails closed if that limiter is unavailable.

```http
POST /api/v1/deployments/{deployment_id}/invoke
Authorization: Bearer ff_live_...
Idempotency-Key: unique-request-001
Content-Type: application/json

{"input":{"ticket":"A-1"}}
```

```http
GET /api/v1/deployments/{deployment_id}/runs/{run_id}
Authorization: Bearer ff_live_...
```

The local demo listens on `http://localhost:8080` and is for development. A public installation needs HTTPS, a protected edge, operational monitoring, workspace-wide quotas, and a backup and key-rotation policy before customer traffic. These endpoints do not expose a browser CORS grant, a webhook or an MCP server interface. The initial hosted targets are executable OpenAI/Gemini agents and published linear workflows using approved local tools.
