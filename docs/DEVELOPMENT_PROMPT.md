# FlowForge AI — complete development prompt

Continue building FlowForge AI in `C:\Users\rhajr\Desktop\FlowForge AI`. This is a new AI Agent Builder and Workflow Automation SaaS. Never access, reuse, migrate or modify ResearchPilot. Read `README.md`, `docs/PROJECT_STATUS.md`, `docs/PRD.md`, `docs/DESIGN.md`, and `docs/technical-architecture/` before changing an unfamiliar area. Preserve user data, untracked reference images and local secrets. Explain each vertical slice in plain language: what users gain, the technical choice, why it is appropriate, and what remains.

## Product and stack

Build a premium responsive enterprise SaaS with dark navy navigation, white workspaces, indigo/purple accents, and a flagship visual workflow builder. Use Next.js App Router, TypeScript, Tailwind CSS, FastAPI, PostgreSQL, Redis, Celery and Docker Compose. Keep the backend a modular monolith. The web app must connect real APIs and show truthful empty, loading, success and failure states. The intended surfaces include marketing, authentication, workspace dashboard, agent library/builder/test/version history, workflow list/builder/validation, run monitoring/history, Tool Registry, Integrations, deployments, settings and usage. No academic research or literature review features.

## Current baseline (21 October 2026)

- Local Compose preview: `http://localhost:8080`, bound to localhost.
- Workspace sessions, roles, CSRF, agent drafts and immutable versions, provider key verification/encryption, Tool Registry with two bounded local read-only tools.
- Live agent runs for OpenAI GPT-5 Mini, Gemini 2.5 Flash, DeepSeek Flash/V4 Pro, Claude Haiku 4.5 and OpenRouter GPT-4o-mini. Other verified models are setup-only until an adapter and price policy exist. Token costs are estimates, not billing guarantees.
- Bounded OpenAI local-tool harness with trace, cancellation, timeout, budget reservation and crash reconciliation.
- Curated MCP Streamable HTTP connection and manual tool test. The operator owns `MCP_CATALOG_JSON`; workspace users cannot submit URLs. Connection snapshots bounded allowlisted tool metadata and input schemas. Operator-reviewed read-only MCP tools can run as published workflow nodes; agent-initiated MCP calls remain future work.
- Five private starter templates. Supported linear workflows with approved local tools and one published tool-free agent can be validated, published and run durably through Celery/PostgreSQL.
- Hosted deployments pin immutable agent or workflow versions. Hashed one-time bearer keys, rotation, revocation, idempotent invoke, polling, per-deployment rate limits and recent run history are implemented for local development.
- Consult `docs/PROJECT_STATUS.md` for test counts and precise limitations; run the checks again after changes.

## Continue in small vertical slices

1. **MCP agent grants and execution.** Let an editor choose an allowlisted, connected read-only MCP tool for an OpenAI GPT-5 Mini agent. Freeze server identity, tool name, connection generation and schema hash in the published version. Validate arguments against the snapshot; check the current allowlist, connection, generation, schema and run limits immediately before each call. Do not send connector secrets to a model or Celery message. Persist intent and safe event metadata; bound remote time, response size and retry behavior. Fail closed on drift, revoke, timeout and unsafe endpoint. Test with a fake MCP server, including duplicate delivery and prompt-injection content. Add UI grant controls and trace states.
2. **Workflow branch and transform nodes.** Build typed conditional paths and safe declarative transforms after the initial one-agent linear path. Persist step state, mappings and selected edges; support cancellation, timeout, safe retry and worker recovery. Keep workflow execution deterministic and replayable from database state. Connect the canvas inspector, validation diagnostics and monitoring UI.
3. **Budgets and tenant fairness.** Add workspace-wide concurrency and spend limits with reservation/reconciliation. Separate actual provider usage, estimates and uncertain cost. Add usage views and tests for simultaneous submissions and crash recovery.
4. **Templates and deployment experience.** Expand reviewed agent/workflow templates with prerequisites and clear install flow. Never copy credentials or grants. Improve deployment docs, scoped keys, run observability and client examples. Public production hosting needs HTTPS, backups, egress controls and security review before exposure beyond localhost.
5. **Hardening and completeness.** Finish role/member administration, pagination, accessible responsive canvas alternatives, logging/metrics, retention, migration/restore rehearsal, CI and all truthful error/loading/empty states. Add more provider models only after verifying current API support and pricing.

## Engineering rules

Deliver each slice across database/API/runtime/UI/docs only where needed. Keep contracts versioned and regenerate frontend API types when OpenAPI changes. Use database state as the source of truth; Celery messages carry IDs. Preserve tenant ownership and immutable publication. Never run arbitrary tenant code, arbitrary stdio MCP processes, or tenant-supplied network URLs on shared workers. Credential material stays encrypted server-side. Remote MCP writes need a separate approval and idempotency/receipt design; do not infer safety from remote annotations. External tool output is untrusted data. Use tight time, size, iteration, cost and concurrency bounds. Prefer a small concrete implementation over a generic framework.

For each slice, run relevant backend tests against Compose PostgreSQL/Redis, frontend tests/typecheck/lint and a production Next.js build when UI changes. Check API readiness and the local preview after deployment. State what was actually tested and whether a real provider/MCP call was made. Update `docs/PROJECT_STATUS.md` and teaching notes. Do not claim the entire product is complete while the listed gaps remain.
