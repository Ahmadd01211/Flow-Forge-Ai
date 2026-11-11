# Project status

Date: 11 November 2026 (Asia/Karachi).

## Finish line

The user confirmed a complete local release first. Public hosting, subscriptions and payment processing are outside this pass. The full product roadmap remains in [development phases](DEVELOPMENT_PHASES.md); bounded local functionality is distinguished from later orchestration and production work.

## Delivered and running locally

- Accounts/workspaces: verification, recovery, invitations, roles, ownership protection and session revocation. Development mail is captured by Mailpit.
- Providers: separate encrypted OpenAI, OpenRouter, Claude, Gemini and DeepSeek keys; refreshable catalogs; eleven reviewed model IDs; backend-owned capability/pricing profiles.
- Agents: guided schemas, publication readiness, immutable versions, comparisons/restore, bounded tool calls, pinned MCP grants under per-tool Allow/Block policies and native tool protocols across all five reviewed provider families.
- Regression examples: encrypted expected input/output suites scored against observed completed runs. Missing evidence is untested; scoring makes no model call.
- Workflow authoring: up to thirty direct DAG steps and four direct agents; nested conditions, multi-way Switch routing, stable Remove duplicates cleanup, fan-out, merges, visual field mappings and pinned reusable subworkflows. For each nodes process up to twenty items sequentially. Expansion is bounded at three workflow levels, 120 steps and eight agent calls.
- Workflow execution: encrypted scoped/item checkpoints, claim fencing, safe recovery, persisted child resource ceilings/deadlines, shared model budgets, local retry policies, cancellation and explicit replay. Completed children are reused even after their own execution window has ended, while new work stays within the active parent deadline. Unknown external outcomes are never automatically replayed.
- Workflow monitoring: Agent/Workflow execution tabs, live progress, failed-step inspection and direct links from the builder/automation history.
- Automations: authenticated JSON webhooks, deduplication/conflict handling, hashed one-time keys, persistent 60–86400-second interval schedules, five-field cron schedules in an IANA timezone with a next-runs preview and an explicit daylight-saving policy, coalesced downtime recovery, pause/resume/archive and rotation.
- Usage: real recorded model cost/tokens, active reservations and uncertain charges; shared transactional admission across agents, workflows, deployments and triggers. Default limits are $10/day, 1,000 accepted runs/day and four active runs, with two per type.
- Templates: reviewed starters plus user saving, independent copies and sharing controls. Private connection bindings are removed from portable copies.
- Hosted API access: version-pinned local endpoints, one-time bearer keys, scoped polling, rotation/revocation and rate limiting.
- HTTP API tools: admin-approved fixed HTTPS destinations/methods, encrypted reusable header credentials, read-only agent grants, published workflow writes, contract checking and SSRF restrictions. Tool Registry separates API tools from local utilities.
- Action starters and portability: fifteen built-in recipes, including local category routing and contact deduplication, webhook actions, scheduled digests, AI priority routing and a working customer-profile/batch pair; setup instructions/sample JSON; versioned private import/export with workspace bindings cleared.
- Recovery operations: password-encrypted database/environment/master-key backup helper and a successful isolated PostgreSQL restore rehearsal. Async workers recheck requester/deployment permissions after admission and between workflow steps.
- Approvals and timers: durable Human approval and Wait nodes park a run without holding a worker; decisions are bound to the scoped node and canonical input hash, with independent review by default. Combined worst-case waits are bounded to 24 hours.
- Activity: owners/admins filter and page workspace audit events and export the displayed page as JSON.
- MCP servers: owners/admins add any public HTTPS MCP server (URL and token encrypted) or connect operator-reviewed ones; read-only tools start allowed and write tools stay blocked until an admin allows them. Agents and workflows can call allowed write tools. Policy is checked at publication, submission and before every call.
- Guided service recipes: GitHub list/create issues and Slack channel messages fill the existing HTTP tool permission form. They use admin-supplied tokens, not OAuth.

## Guided workbench additions (11 November 2026)

The guided agent/workflow workbench is implemented on the existing authoring and execution platform. The changes are organized along these current seams:

- **Workspace overview:** `workspaces/overview.py` provides workspace-scoped summary data; the overview dashboard and model render the resulting activity and suggested next steps.
- **Agent authoring:** `agents/workbench.py`, `assist.py`, and `managed.py` own workbench and assistant operations; the agent editor, builder blocks, chat, starter flows and test panel use the existing agent draft, validation and publication contracts.
- **Workflow authoring:** `workflows/chat.py`, `llm.py`, `tools.py`, and node configuration extend the existing graph editor and runtime with bounded assistant/model/tool nodes. Workflow chat suggestions still enter the normal draft and validation path.
- **Skills and memory:** the skills module provides workspace-scoped skill resources. Conversation memory uses its own persistence and remains separate from published definitions and execution records.
- **Run evidence:** the execution trace service records safe events and feedback against durable runs; the run detail, trace and feedback components display persisted evidence.
- **Persistence and API contract:** migrations `0026` through `0032` add workflow model agents, conversation memory, run source, agent playground, skills, run traces/feedback and builder assistants. `backend/openapi.json` and generated frontend types include the current API contract.

The original guided workbench baseline was a broad 106-file integration commit on `feature/local-release-continuation` (`3d1b4f2`), not an uncommitted working tree. That baseline reported migration `0032 (head)`; current source also includes `0033_agent_tool_approvals.py`. This documentation update does not certify the applied database revision.

## Guided creation and provider readiness (11 November 2026)

- Source inventory: **15 built-in recipes**, **11 starter skills**, and **22 workflow node types**. Recipes are assembled in `backend/app/modules/templates/catalog.py` with action, approval, composition and practical starters; skills are in `backend/app/modules/skills/catalog.py`; node types are defined in `backend/app/modules/workflows/schemas.py`.
- Task recipes support local goal search, category filtering and a Recommended result. Preview shows setup, expected output, sample input where supplied, and run guidance before **Create workspace draft**. Preview/search make no model call. Customer reply draft and Meeting action items provide agent starters; Route requests by category and Remove duplicate contacts add reproducible local workflow examples.
- Created agents/workflows and copied skills are workspace-visible editable drafts. The creation handoff links each attached skill for review and publication before agent testing or publication. Skill edits require a new immutable skill version and another agent readiness review.
- Integrations keeps provider/key setup available with zero connected providers. Owners/admins can verify their own key, refresh the saved-key model catalog, search models and save a default. Model listing verifies access to a catalog; generation access and billing capacity still require a real accepted test. Setup-only models remain distinct from runnable models.
- Local workflow **Preview** executes supported saved-draft steps without a durable full run. Agent/model/external-service/approval/timer steps require **Publish** followed by **Run**; publication alone does not execute anything.
- Approval inside the agent tool loop is delivered for write-capable MCP calls: encrypted exact-call context, independent owner/admin review, durable worker continuation, permission rechecks, expiry and outcome handling are implemented in `executions/agent_approvals.py`, with migration `0033` and regression coverage in `test_agent_tool_approvals.py`.

Recorded guided-creation automated verification (11 November 2026, before the website refresh): PostgreSQL/Redis backend suite **355 passed in 120.83s** with the backend source explicitly mounted, Ruff clean; frontend Vitest **73 tests across 20 files**, ESLint, API drift check, Webpack production build and standalone TypeScript typecheck passed. Source inventory, checklist route files and local Markdown links were checked. Tests use controlled provider responses; these checks do not certify real-account generation or signed-in GUI behavior.

Website refresh documentation audit (11 November 2026): source catalog/schema counts, registration/workspace routes, editor controls and local Markdown links were checked. The manual guide now includes Switch/default routing and first-record contact deduplication. These source checks do not rerun the application suites or certify the running stack. Earlier test totals below describe their own slices.

The final signed-in GUI walkthrough and real-provider acceptance remain for the user. Follow [noncoder creation checks](manual-testing/noncoder-creation.md) with your own credential through Integrations. No live-provider success is asserted by this documentation update.

## Historical verification evidence

The results below record earlier slices; they are not fresh acceptance evidence for the guided creation follow-up.

The full PostgreSQL/Redis suite passed 270 tests, including eighteen new composition cases. Eighteen frontend tests cover nested preview controls and deterministic server timestamps, alongside existing editor tests. Lint, type checking, generated API drift checks and production builds pass. A fresh Celery process completes a DAG through real Redis/PostgreSQL. The live stack also completed a two-customer batch with all nine scoped checkpoints; preview/durable outputs matched by JSON value. API readiness checks migrations, PostgreSQL and Redis. Encrypted backup and isolated restore rehearsal passed against migration 0022 without replacing live data.

Guided workbench verification (11 November 2026): `docker compose --profile test run --rm --build tests` passed **334 tests** in 140.68 seconds; `docker compose --profile test run --rm tests ruff check app tests migrations scripts` reported “All checks passed!”. Frontend Vitest passed **40 tests across 13 files**; ESLint, standalone TypeScript typecheck, API/OpenAPI drift check, and the Webpack production build passed. The first typecheck invocation overlapped the build and read regenerated `.next/types`; it was rerun alone after the build and passed. The local Compose stack reports API healthy, migration `0032 (head)`, `/health/ready` returns `{"status":"ready"}`, and the application root returns HTTP 200 at `http://localhost:8080`.

Guided first-run follow-up (11 November 2026): support-triage template preview now includes setup steps and sample input, covered by `backend/tests/test_templates.py`. Fresh checks passed: isolated PostgreSQL/Redis suite **334 passed in 109.99s**, Ruff, frontend Vitest **45 tests across 15 files**, ESLint, TypeScript typecheck, API/OpenAPI drift, and Webpack production build. Local Compose is healthy; `/health/ready` returned `{"status":"ready"}`, Alembic reports `0032 (head)`, and `http://localhost:8080` returned HTTP 200. The final browser GUI walkthrough remains for the user; see [guided first run](learning/24-GUIDED-FIRST-RUN.md).

MCP workflow picker (11 November 2026): the workflow **MCP tool** step now searches allowed tools by server, name, or description; groups results by server; and shows the connection's read-only/write metadata. It preserves the existing `{server_id, tool_name}` workflow configuration and permission boundary. Final frontend verification passed: Vitest **52 tests across 17 files**, ESLint, TypeScript typecheck, API drift check, and Webpack production build; backend PostgreSQL/Redis suite **334 passed in 215.44s** and Ruff clean. Local Compose readiness returned `{"status":"ready"}`, Alembic reports `0032 (head)`, and the app returned HTTP 200. Review fixes keep arrow-key results visible and the active descendant valid after filtering. Final GUI check is left to the user; see the [manual picker walkthrough](learning/25-MCP-TOOL-PICKER.md).

An additional interactive signed-in browser smoke check was not completed in this session because the computer-use browser host was unavailable. Browser-level verification remains outstanding; no provider credentials or real external model calls were used.

The earlier guided workbench verification recorded migrations through `0032` applied locally. Current source additionally contains migration `0033` for agent tool approvals. Earlier migrations cover templates, examples, automation bindings, usage controls, workflow composition, schedules, tools, approvals and workspace policy; migrations `0026`–`0032` add the guided workbench capabilities listed above. Existing immutable version JSON/hashes and encrypted evidence are preserved. New child scopes retain their original budget/deadline through recovery; older completed runs have no retroactively generated step input.

The local stack is available at http://localhost:8080. Signed-in HTTP smoke checks cover editors, settings, integrations, API tools, templates, workflow executions, automations and usage. No shared demo password is provided. Disposable accounts were used for browser checks of Tool Registry, the loop builder/preview and per-item execution evidence. Timestamp hydration mismatches and clipped trace badges were corrected. The dashboard now shows real recorded usage rather than an obsolete runtime placeholder. Windows-mounted source refresh was changed to Webpack polling after stale rendered code was observed; this is the supported local development path.

Cron slice (1 November 2026): the full PostgreSQL/Redis suite passed 295 tests, including six cron cases covering validation, leap days, spring-forward and fall-back rules, downtime coalescing, the preview endpoint and the database constraint. Migration 0024 was downgraded and re-applied on the test database. Ruff, frontend lint/type checks, 21 frontend tests, API drift checks and the production build pass. On the live stack, a disposable account previewed, created, listed and archived a weekday Asia/Karachi schedule through the nginx edge, and the automations page rendered its cadence; the account's sessions were then revoked.

MCP slice (1 November 2026): two client bugs that made every real MCP connection fail (SDK 2.x snake_case fields) and hid tool errors (`isError`) were fixed. The full suite passed 303 tests, including eight workspace-server cases; migration 0025 round-tripped. A live run against the deployed stack added the public DeepWiki MCP server, ran a published workflow through the Celery worker with real output, then blocked the tool and confirmed new runs were refused. No credentialed MCP server or paid model call was used.

Before the MCP slice, no real provider credential, external mailbox, MCP server or paid model call was used to certify these adapters. Native provider contracts and failures are tested with controlled responses; real account/service acceptance remains distinct.

## Remaining work

General while-loops, richer expressions, signed vendor webhook receivers, fine-grained resource permissions and OAuth remain visible roadmap items. Waits longer than 24 hours are not supported. HTTP service recipes use existing admin-supplied credentials; Slack/GitHub acceptance has not been tested against real accounts. Subscription billing and public hosting are excluded from this local-first pass. Public use additionally requires operator-owned plan ceilings, HTTPS, managed backup/key-rotation operations, network egress policy, load/capacity isolation and external security review. The local backup helper is capped at 256 MiB and provides isolated restore verification rather than live replacement or point-in-time recovery.

Workspace owners/admins add MCP servers themselves; the operator catalog is optional and can lock installs to reviewed servers only. GitHub's hosted MCP server connects with a fine-grained token via a quick-setup preset; tool lists are paged up to 250 tools, and `anyOf` schemas are supported (`$ref` tools are still skipped). Rejected tokens are reported as `MCP_AUTH_FAILED`, verified against GitHub's live server with invalid tokens. No valid GitHub token was used, so authenticated GitHub tool calls remain to be accepted by the user. Write-capable MCP calls now support durable independent approval inside an agent's own tool loop; MCP OAuth remains unimplemented. Owners/admins supply their own keys through the local interface. Never paste a credential into a support conversation.

## Walkthroughs

- [Noncoder recipe, skill, provider and workflow GUI checks](manual-testing/noncoder-creation.md)
- [Guided first run and manual GUI checklist](learning/24-GUIDED-FIRST-RUN.md)
- [Search and select MCP tools in workflows](learning/25-MCP-TOOL-PICKER.md)
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

Repository: `Ahmadd01211/Flow-Forge-Ai`, branch `feature/local-release-continuation`, at commit `3d1b4f2` for the verified baseline. That branch is pushed to GitHub; `main` remains unchanged. That statement describes the baseline only; later changes and their evidence are recorded separately. Secrets and generated build data are ignored. The old ResearchPilot project was not accessed.

