# Project status

Date: 1 November 2026 (Asia/Karachi).

## Finish line

The user confirmed a complete local release first. Public hosting, subscriptions and payment processing are outside this pass. The full product roadmap remains in [development phases](DEVELOPMENT_PHASES.md); bounded local functionality is distinguished from later orchestration and production work.

## Delivered and running locally

- Accounts/workspaces: verification, recovery, invitations, roles, ownership protection and session revocation. Development mail is captured by Mailpit.
- Providers: separate encrypted OpenAI, OpenRouter, Claude, Gemini and DeepSeek keys; refreshable catalogs; eleven reviewed model IDs; backend-owned capability/pricing profiles.
- Agents: guided schemas, publication readiness, immutable versions, comparisons/restore, bounded tool calls, pinned MCP grants under per-tool Allow/Block policies and native tool protocols across all five reviewed provider families.
- Regression examples: encrypted expected input/output suites scored against observed completed runs. Missing evidence is untested; scoring makes no model call.
- Workflow authoring: up to thirty direct DAG steps and four direct agents; nested conditions, fan-out, merges, visual field mappings and pinned reusable subworkflows. For each nodes process up to twenty items sequentially. Expansion is bounded at three workflow levels, 120 steps and eight agent calls.
- Workflow execution: encrypted scoped/item checkpoints, claim fencing, safe recovery, persisted child resource ceilings/deadlines, shared model budgets, local retry policies, cancellation and explicit replay. Completed children are reused even after their own execution window has ended, while new work stays within the active parent deadline. Unknown external outcomes are never automatically replayed.
- Workflow monitoring: Agent/Workflow execution tabs, live progress, failed-step inspection and direct links from the builder/automation history.
- Automations: authenticated JSON webhooks, deduplication/conflict handling, hashed one-time keys, persistent 60–86400-second interval schedules, five-field cron schedules in an IANA timezone with a next-runs preview and an explicit daylight-saving policy, coalesced downtime recovery, pause/resume/archive and rotation.
- Usage: real recorded model cost/tokens, active reservations and uncertain charges; shared transactional admission across agents, workflows, deployments and triggers. Default limits are $10/day, 1,000 accepted runs/day and four active runs, with two per type.
- Templates: reviewed starters plus user saving, independent copies and sharing controls. Private connection bindings are removed from portable copies.
- Hosted API access: version-pinned local endpoints, one-time bearer keys, scoped polling, rotation/revocation and rate limiting.
- HTTP API tools: admin-approved fixed HTTPS destinations/methods, encrypted reusable header credentials, read-only agent grants, published workflow writes, contract checking and SSRF restrictions. Tool Registry separates API tools from local utilities.
- Action starters and portability: ten built-in templates, including webhook actions, scheduled digests, AI priority routing and a working customer-profile/batch pair; setup instructions/sample JSON; versioned private import/export with workspace bindings cleared.
- Recovery operations: password-encrypted database/environment/master-key backup helper and a successful isolated PostgreSQL restore rehearsal. Async workers recheck requester/deployment permissions after admission and between workflow steps.
- Approvals and timers: durable Human approval and Wait nodes park a run without holding a worker; decisions are bound to the scoped node and canonical input hash, with independent review by default. Combined worst-case waits are bounded to 24 hours.
- Activity: owners/admins filter and page workspace audit events and export the displayed page as JSON.
- MCP servers: owners/admins add any public HTTPS MCP server (URL and token encrypted) or connect operator-reviewed ones; read-only tools start allowed and write tools stay blocked until an admin allows them. Agents and workflows can call allowed write tools. Policy is checked at publication, submission and before every call.
- Guided service recipes: GitHub list/create issues and Slack channel messages fill the existing HTTP tool permission form. They use admin-supplied tokens, not OAuth.

## Evidence

The full PostgreSQL/Redis suite passed 270 tests, including eighteen new composition cases. Eighteen frontend tests cover nested preview controls and deterministic server timestamps, alongside existing editor tests. Lint, type checking, generated API drift checks and production builds pass. A fresh Celery process completes a DAG through real Redis/PostgreSQL. The live stack also completed a two-customer batch with all nine scoped checkpoints; preview/durable outputs matched by JSON value. API readiness checks migrations, PostgreSQL and Redis. Encrypted backup and isolated restore rehearsal passed against migration 0022 without replacing live data.

Migrations through 0024 are applied: user templates (0016), encrypted agent examples (0017), automation bindings (0018), quotas/reservations (0019), encrypted checkpoints (0020), approved HTTP tools (0021), the expanded checkpoint bound (0022), workflow pauses (0023), cron schedules (0024) and workspace MCP servers/tool policies (0025). Existing immutable version JSON/hashes and encrypted evidence are preserved. New child scopes retain their original budget/deadline through recovery; older completed runs have no retroactively generated step input.

The local stack is available at http://localhost:8080. Signed-in HTTP smoke checks cover editors, settings, integrations, API tools, templates, workflow executions, automations and usage. No shared demo password is provided. Disposable accounts were used for browser checks of Tool Registry, the loop builder/preview and per-item execution evidence. Timestamp hydration mismatches and clipped trace badges were corrected. The dashboard now shows real recorded usage rather than an obsolete runtime placeholder. Windows-mounted source refresh was changed to Webpack polling after stale rendered code was observed; this is the supported local development path.

Cron slice (1 November 2026): the full PostgreSQL/Redis suite passed 295 tests, including six cron cases covering validation, leap days, spring-forward and fall-back rules, downtime coalescing, the preview endpoint and the database constraint. Migration 0024 was downgraded and re-applied on the test database. Ruff, frontend lint/type checks, 21 frontend tests, API drift checks and the production build pass. On the live stack, a disposable account previewed, created, listed and archived a weekday Asia/Karachi schedule through the nginx edge, and the automations page rendered its cadence; the account's sessions were then revoked.

MCP slice (1 November 2026): two client bugs that made every real MCP connection fail (SDK 2.x snake_case fields) and hid tool errors (`isError`) were fixed. The full suite passed 303 tests, including eight workspace-server cases; migration 0025 round-tripped. A live run against the deployed stack added the public DeepWiki MCP server, ran a published workflow through the Celery worker with real output, then blocked the tool and confirmed new runs were refused. No credentialed MCP server or paid model call was used.

Before the MCP slice, no real provider credential, external mailbox, MCP server or paid model call was used to certify these adapters. Native provider contracts and failures are tested with controlled responses; real account/service acceptance remains distinct.

## Remaining work

General while-loops, richer expressions, signed vendor webhook receivers, fine-grained resource permissions and OAuth remain visible roadmap items. Waits longer than 24 hours are not supported. HTTP service recipes use existing admin-supplied credentials; Slack/GitHub acceptance has not been tested against real accounts. Subscription billing and public hosting are excluded from this local-first pass. Public use additionally requires operator-owned plan ceilings, HTTPS, managed backup/key-rotation operations, network egress policy, load/capacity isolation and external security review. The local backup helper is capped at 256 MiB and provides isolated restore verification rather than live replacement or point-in-time recovery.

Workspace owners/admins add MCP servers themselves; the operator catalog is optional and can lock installs to reviewed servers only. MCP tools whose schemas use `anyOf`, `$ref` or `pattern` are skipped for now. Approval inside an agent's own tool loop and MCP OAuth are not yet implemented. Owners/admins supply their own keys through the local interface. Never paste a credential into a support conversation.

## Walkthroughs

- [Agent MCP, provider tools and regression evidence](learning/12-AGENT-MCP-AND-REGRESSIONS.md)
- [Real webhooks and schedules](learning/13-WEBHOOKS-AND-SCHEDULES.md)
- [Workspace usage and admission limits](learning/14-WORKSPACE-USAGE-LIMITS.md)
- [Workflow graphs, joins and mappings](learning/15-WORKFLOW-GRAPHS-AND-MAPPINGS.md)
- [Checkpoints, recovery, policies and debugger](learning/16-WORKFLOW-CHECKPOINTS-AND-DEBUGGER.md)
- [HTTP API tools, actions and portable template files](learning/17-HTTP-API-TOOLS-AND-TEMPLATE-FILES.md)
- [Local release checks and encrypted recovery](learning/18-LOCAL-RELEASE-AND-RECOVERY.md)
- [Bounded loops, reusable workflows and per-item evidence](learning/19-WORKFLOW-LOOPS-AND-SUBWORKFLOWS.md)
- [Human approvals, durable timers and workspace activity](learning/20-APPROVALS-TIMERS-AND-ACTIVITY.md)
- [Guided GitHub and Slack tools](learning/21-GUIDED-SERVICE-CONNECTORS.md)
- [Calendar (cron) schedules](learning/22-CRON-SCHEDULES.md)
- [Workspace MCP servers and tool policies](learning/23-WORKSPACE-MCP-SERVERS.md)

Repository: separate Git repository on main with an initial commit and ongoing uncommitted development. Pre-existing user work was preserved. Secrets and generated build data are ignored. The old ResearchPilot project was not accessed.

