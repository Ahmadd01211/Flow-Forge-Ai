# FlowForge AI

An independent AI agent builder and workflow automation platform.

Agent authoring: guided schema fields, tool argument/permission inspection, publication readiness checks and versioned output-token ceilings are available in the editor. See [agent-builder walkthrough](docs/learning/11-AGENT-BUILDER.md).

Guided first run: start from Overview → **Choose a task**, preview the recommended support-triage agent, and follow the [manual first-run checklist](docs/learning/24-GUIDED-FIRST-RUN.md). Live model runs require your provider key and may incur charges.

User templates: save a draft in the agent editor or visual workflow builder, then choose **Save as template**. Enter a name, description and category; access defaults to **Only me**. Choose workspace members or everyone signed in to share. The Templates gallery supports previews, independent editable copies, and creator-controlled sharing changes. Revoking sharing blocks future access and copies; existing copies remain independent. Review instructions and fixed values before sharing. Stored credentials are excluded, and copied agent, MCP, HTTP and trigger steps require configuration. Database migration `0016` is required; the normal Docker Compose startup applies it.

Provider capabilities: Integrations now shows backend-owned execution/tool support and estimated token rates for 11 reviewed model IDs across the five providers. Refresh a model list using the saved key without rotating it. Other provider-listed models remain labeled setup only. See [supported scope and provider sources](docs/learning/10-PROVIDER-CAPABILITIES.md).

Usage & budgets now shows actual recorded usage, active reservations and uncertain charges across agents/workflows. Owners/admins can set shared daily model budgets, accepted-run limits and active capacity. These apply equally to interactive runs, hosted calls, webhooks and schedules. Defaults are $10/day and 1,000 accepted runs/day; see [usage policy and limitations](docs/learning/14-WORKSPACE-USAGE-LIMITS.md). Compose applies migrations through `0032` at startup.

MCP servers: owners/admins choose **Integrations → MCP servers → Add server** to connect any public HTTPS MCP server. Read-only tools start allowed; write tools stay blocked until allowed per tool. See [workspace MCP servers and tool policies](docs/learning/23-WORKSPACE-MCP-SERVERS.md).

Calendar schedules: in **Triggers & schedules**, choose **Calendar (cron)** for rules such as `0 9 * * 1-5` in a chosen timezone, and preview the next five runs before saving. See [cron schedules and daylight-saving behavior](docs/learning/22-CRON-SCHEDULES.md).

Accounts and teams: Settings now supports email verification, invitations, member roles/removal, ownership transfer, workspace creation/rename, password changes and signing out all devices. Password recovery starts from sign-in. Development emails appear at http://localhost:8025; configure SMTP for public delivery. See [accounts walkthrough](docs/learning/09-ACCOUNTS-AND-WORKSPACES.md) and [development phases](docs/DEVELOPMENT_PHASES.md).

**Required stack:** Next.js App Router + TypeScript frontend; Python + FastAPI backend. PostgreSQL is the source of truth. Redis handles authentication rate limits and Celery task delivery.

## Run locally

FlowForge AI is running at **http://localhost:8080**. Create an account to explore your workspace; no default password or shared demo account is installed.

For a fresh setup with Docker Desktop running:

```powershell
python scripts/init-env.py
docker compose up -d --build
```

The initializer preserves an existing `.env` and generates local secrets without printing them. `.env` is ignored by Git. On this workstation, an ignored local environment has already been generated. Use `docker compose stop` to stop services while preserving data; no volume-deletion command is needed.

## Current implementation

- Accounts, recovery, email verification, teams, invitations and workspace roles.
- Five provider connections with encrypted keys and eleven reviewed model profiles; bounded native tool protocols for OpenAI, OpenRouter, Claude, Gemini and DeepSeek.
- Agent authoring, immutable versions, regression examples, MCP grants under per-tool Allow/Block policies and read-only HTTP grants.
- Visual workflows with up to thirty direct steps/four agents, branches, merges, field mappings, bounded For each loops and pinned reusable workflow calls. Expansion is limited to three workflow levels, 120 steps and eight agent calls.
- Durable runs with encrypted checkpoints, safe recovery, cancellation, local retry policies, explicit replay and step debugging.
- Authenticated JSON webhooks, interval and cron schedules, pinned deployment endpoints and shared usage/admission budgets.
- Durable human approvals and timers, plus an owner/admin activity log with JSON export.
- Guided GitHub and Slack recipes on top of approved HTTP tools.
- Admin-approved HTTPS API tools with encrypted reusable header credentials and durable workflow action receipts.
- Ten starter templates, including a working child/batch pair and service actions, plus user saving/sharing and portable private JSON import/export.
- Docker Compose, PostgreSQL migrations through 0032, separate DB roles, contract generation, CI and an encrypted backup/isolated restore helper.
- Guided agent workbench with reviewable assistant proposals, conversation memory, workspace skills and tool-aware testing.
- Workflow chat and bounded model/tool nodes that remain within the existing graph validation and durable run path.
- Workspace activity overview plus durable run traces and feedback tied to execution evidence.
- OpenAPI contract and generated frontend types include the current workbench endpoints; local migration head is `0032`.

Open **Tool Registry → HTTP API tools** to connect a fixed destination. Agents receive reviewed read-only GET grants; write actions execute through published workflows. Credentials never belong in instructions or URLs. Model budgets exclude service API charges. See [API tools and template files](docs/learning/17-HTTP-API-TOOLS-AND-TEMPLATE-FILES.md).

To try a workflow, preview a starter in **Templates**, connect its required tools/agent versions, validate, publish and run. **Executions → Workflows** shows step evidence. **Triggers & schedules** binds a published version to a webhook or persistent interval. The operator-curated MCP catalog is empty by default; remote servers must be explicitly configured through `MCP_CATALOG_JSON`.

For another app, create a **Deployment** from a published version and keep its one-time key on your app server. Local endpoints use idempotent submission and scoped polling. No provider key is bundled: enter your own key in Integrations. Real provider/service calls may incur charges.

The local milestone remains bounded. General while-loops, richer expressions, signed vendor webhooks, fine-grained permissions and OAuth remain on the [phase roadmap](docs/DEVELOPMENT_PHASES.md). Public hosting and subscription billing are outside this local-first pass. Real upstream acceptance, operator quotas, capacity isolation and security operations must be addressed before serving customers.

Try the new composition phase using **Prepare a customer profile**, publish it, then connect its version in **Batch customer profiles**. Preview with the template's sample JSON and inspect item receipts in **Executions → Workflows**. See the [step-by-step walkthrough and design decisions](docs/learning/19-WORKFLOW-LOOPS-AND-SUBWORKFLOWS.md).

## Checks

```powershell
docker compose --profile test run --rm --build tests
docker compose --profile test run --rm tests ruff check app tests migrations scripts
cd frontend
npm ci
npm run lint
npm run typecheck
npm run test
npm run api:check
npm run build
```

Integration tests use the isolated `flowforge_test` database and refuse to reset any database without the `_test` suffix. Frontend builds explicitly use Webpack because this workstation's Turbopack CSS worker failed; the supported Webpack production build passes. Focused browser review uses a disposable account. The local development server uses Webpack polling so edits on the Windows-mounted source directory refresh reliably.

## Architecture and learning

Start with the [final technical architecture proposal](docs/technical-architecture/README.md) and the approved [product and screen design](docs/DESIGN.md). The final package supersedes the initial technical sketches where they differ.

The original JPG references remain unchanged in the project root. No previous project was inspected or reused.

Status and evidence: [current project status](docs/PROJECT_STATUS.md). Walkthroughs explain the decisions and their limits, including [DAG authoring](docs/learning/15-WORKFLOW-GRAPHS-AND-MAPPINGS.md), [durable execution](docs/learning/16-WORKFLOW-CHECKPOINTS-AND-DEBUGGER.md) and [local release/backup recovery](docs/learning/18-LOCAL-RELEASE-AND-RECOVERY.md).

## API contract generation

Run `python scripts/export_openapi.py` from the backend environment to refresh `backend/openapi.json`, then `npm run api:generate` from frontend. CI checks both exports for drift. Agent, snapshot and contract-playground TypeScript types now come from OpenAPI; remaining workflow/session types will move as their contracts mature.

## Documents

- [Screen design, tokens, components and navigation](docs/DESIGN.md)
- [MVP PRD and acceptance criteria](docs/PRD.md)
- [C4 architecture and worker topology](docs/ARCHITECTURE.md)
- [Database ER model](docs/DATABASE.md)
- [REST contracts](docs/API.md)
- [Agent state machine and workflow execution](docs/EXECUTION_MODEL.md)
- [Security threat model](docs/SECURITY.md)
- [Implementation backlog](docs/ROADMAP.md)
- [Current status](docs/PROJECT_STATUS.md)
- [Architecture decisions](docs/adr/0001-control-and-execution-planes.md)
- [Tools, MCP connections and hosted deployment sequence](docs/technical-architecture/09-TOOLS-MCP-AND-DEPLOYMENTS.md)
- [Complete development prompt and next slices](docs/DEVELOPMENT_PROMPT.md)
- [Published agent steps in linear workflows](docs/learning/08-WORKFLOW-AGENT-STEPS.md)



