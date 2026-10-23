# MVP product requirements

## Outcome

A developer or operations team can configure a bounded AI agent, test it, pin its version inside a validated workflow and inspect a real execution. No academic research or literature review features.

Primary users: developers, automation freelancers, small businesses, agencies and operations teams. First use case: manually submit a support ticket, classify it, route by priority and return structured output. External notifications are deferred until a supported connector exists.

## Scope and acceptance

| Capability | Acceptance criteria |
|---|---|
| Identity/workspaces | Register/login/logout with server sessions; create workspace; owner/admin/editor/viewer roles; unauthorized cross-workspace resource access fails on every endpoint. |
| Agents | Create/edit draft; validate schemas, model capabilities, tools and positive bounded limits; create immutable versions; duplicate/archive without deleting history. |
| Playground | Submit schema-valid input against pinned version; receive queued run ID; inspect real events/output; cancel; failures never render as success. |
| Tools | Register approved tools with schemas, scopes, timeouts and secret references; enforce grants before each invocation; no arbitrary shell/filesystem/database access. |
| Workflow definitions | Persist nodes, edges, positions and mappings; detect cycles, unreachable nodes, missing config, invalid mappings and unsupported versions; publish immutable revision. |
| Workflow execution | Enqueue after durable run creation; resolve dependencies/branches; persist attempts and events; bounded retries, deadlines, cost and cancellation; inspect history. |
| UI | All 15 routes in DESIGN.md connected; keyboard-accessible builder alternatives; responsive views; honest empty/loading/error states. |
| Usage | Track actual provider-reported usage and known estimates separately; enforce run and workspace budgets; never show fabricated accuracy/confidence metrics. |

## Release boundaries

MVP includes one provider adapter selected during provider implementation and a deterministic test adapter clearly identified as test-only. A successful test adapter run is not evidence of a live model integration. No credentials required for design review.

Deferred: schedules, webhooks, OAuth marketplace, human approval queues, multi-agent collaboration, billing, unrestricted user code, Temporal. Consequential write tools remain disabled until an explicit authorization/approval mechanism is implemented.

## Success measurements

Measure first-agent completion, first successful workflow, validation repair time, runtime failure rate, queue latency and usage reconciliation. Establish numeric targets from real pilot observations; do not invent baseline performance.

## Definition of done per vertical slice

Requirements and contracts agreed; migration and API implemented; role checks tested; connected frontend handles all states; relevant automated tests and production build pass; documentation updated. No automated browser screenshot testing unless requested.
