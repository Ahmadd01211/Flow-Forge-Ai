# FlowForge AI

An independent AI agent builder and workflow automation platform.

Agent authoring: guided schema fields, tool argument/permission inspection, publication readiness checks and versioned output-token ceilings are available in the editor. See [agent-builder walkthrough](docs/learning/11-AGENT-BUILDER.md).

Provider capabilities: Integrations now shows backend-owned execution/tool support and estimated token rates for 11 reviewed model IDs across the five providers. Refresh a model list using the saved key without rotating it. Other provider-listed models remain labeled setup only. See [supported scope and provider sources](docs/learning/10-PROVIDER-CAPABILITIES.md).

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

- Next.js App Router, TypeScript, Tailwind, reusable UI primitives and responsive navy/white product styling.
- Registration/login/logout, Argon2id passwords, opaque HttpOnly sessions, CSRF/Origin validation and Redis authentication rate limiting.
- Owned workspace, dashboard with real draft counts, private agent drafts and bounded configuration fields.
- Immutable agent test snapshots with history, configuration comparisons, restore into a new draft revision, database-level immutability and append-only audit records.
- Offline contract playground validates manually supplied input/output examples against a snapshot, with bounded JSON Schema checks and field-level errors. It does not run a model or retain examples.
- Owner/admin connection setup for OpenAI, OpenRouter, Claude, Gemini and DeepSeek, with verification, encrypted credential storage, rotation and revocation. Editors can publish immutable agent definitions after model and schema checks.
- Published selected OpenAI, OpenRouter, Claude, Gemini and DeepSeek agent runs with encrypted input/output, idempotent submission, bounded output, cancellation, usage reporting, a durable queue and worker recovery.
- Reviewed Tool Registry with workspace approvals, bounded local tool tests, immutable agent tool grants, a controlled OpenAI tool-call harness and metadata-only execution traces.
- Operator-curated MCP Streamable HTTP connections with encrypted workspace bearer tokens, exact tool allowlists and bounded remote tool tests.
- Five curated agent/workflow starter templates and a bounded linear workflow draft preview with approved local tools.
- Saved workflow drafts with XYFlow canvas, node palette, inspector, connection editing, undo and keyboard-friendly step list.
- Backend structural graph validation for cycles, connectivity, endpoints, ports and unavailable dependencies. Validation is explicitly not publication readiness.
- Alembic migration, separate application/migration DB users, Docker Compose, locked dependencies and CI configuration.

Agent-initiated MCP calls, multiple agent nodes per workflow and production key rotation are not implemented yet. Run costs are estimates until provider usage is known, and uncertain model outcomes preserve a possible-charge estimate. Draft collection APIs currently return up to 100 drafts; version history has cursor pagination. This is a local development milestone, not a production-ready release.

To try the new slice: save an agent with instructions → **Create snapshot** → **History** → **Validate example data**. Restore copies a selected snapshot into a new draft revision, after confirmation, without changing historical snapshots.

The provider slice adds **Integrations → Verify and connect** for OpenAI, OpenRouter, Claude, Gemini and DeepSeek workspace keys. Then select a provider and listed model in an agent draft, save, and **Publish version**. Verification does not generate output; no API key is bundled with the project. Enter your own key only in the local Integrations form. The ignored `.local/secrets/credential-master.key` file protects stored credentials and must be backed up separately from the database in any deployment.

To try a live run, publish a version using a model marked Live runs, open its **History** tab, select **Run agent**, and enter input JSON. This makes a real provider request with your connected key and may incur charges. The **Runs** page shows state and outcome. Additional listed models require an execution adapter and price policy before they can run.

To expose a published version to another app, open **Deployments**, choose the version, and copy the one-time API key into your app server. See [hosted deployments](docs/learning/07-HOSTED-DEPLOYMENTS.md) for the invoke and polling contract. To try tools, approve a handler in **Tool Registry**, then select it in an OpenAI GPT-5 Mini agent draft before publishing. The **Runs** page shows each model and tool step. To run a workflow, open the **Text cleanup** template, approve `text.replace`, then use **Publish** and **Run** in the builder. You can also insert one **AI agent** node and select a published version; tool-using OpenAI GPT-5 Mini agents are supported. **Preview** runs local nodes; agent and MCP steps require a published durable run. The MCP section of **Integrations** lists only servers explicitly added by the platform operator through `MCP_CATALOG_JSON`; the default local installation has no remote server configured. An operator can mark a reviewed tool with `read_only_tools` to make it selectable as an **MCP tool** workflow node.

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

Integration tests use the isolated `flowforge_test` database and refuse to reset any database without the `_test` suffix. Frontend builds explicitly use Webpack because this workstation's Turbopack CSS worker failed; the supported Webpack production build passes. No screenshot automation was performed.

## Architecture and learning

Start with the [final technical architecture proposal](docs/technical-architecture/README.md) and the approved [product and screen design](docs/DESIGN.md). The final package supersedes the initial technical sketches where they differ.

The original JPG references remain unchanged in the project root. No previous project was inspected or reused.

Status: foundation, editable drafts, immutable agent snapshots, five provider connections, OpenAI, Gemini, DeepSeek, Claude Haiku and OpenRouter GPT-4o-mini live agent runs, local tool harness, MCP connection setup, templates, workflow preview, durable linear workflow runs with one published agent step and hosted development endpoints implemented. See [current status](docs/PROJECT_STATUS.md), [the foundation walkthrough](docs/learning/01-foundation.md), [the snapshot/contract lesson](docs/learning/02-agent-snapshots.md), [the provider lesson](docs/learning/03-provider-connections.md), [the run lesson](docs/learning/04-agent-runs.md), [the harness lesson](docs/learning/05-AGENT-HARNESS.md) [the MCP/templates/preview lesson](docs/learning/06-MCP-TEMPLATES-WORKFLOW-PREVIEW.md) and [the hosted deployment lesson](docs/learning/07-HOSTED-DEPLOYMENTS.md).

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



