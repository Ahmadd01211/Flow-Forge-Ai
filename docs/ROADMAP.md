# Implementation backlog

Initial sketch, superseded by the [final implementation and learning guide](technical-architecture/08-IMPLEMENTATION-AND-LEARNING.md). The current post-agent-run sequence is updated in [tools, MCP and deployments](technical-architecture/09-TOOLS-MCP-AND-DEPLOYMENTS.md): registry and approved tools → MCP read connector → workflow tool runtime → hosted deployments → templates.

Each slice includes contract, migration, backend, frontend, tests and documentation. No application implementation starts before approval of this package.

| Order | Slice | Deliverable and acceptance gate |
|---|---|---|
| 1 | Foundation | Independent Git repo; Next.js/TypeScript/Tailwind/shadcn frontend; FastAPI/Pydantic backend; Compose/Postgres/Redis; CI typecheck, lint, build and backend tests; health checks and environment examples. |
| 2 | Identity/workspace | Complete register/login/logout/session and workspace ownership slice; role tests and real empty dashboard. |
| 3 | Agent definitions | Schema/limits/tools draft editor, immutable versions, library, detail and version history; save conflicts and authorization covered. |
| 4 | Provider adapter | One selected provider with capability registry and structured output; server-only credentials; deterministic test adapter; no unsupported model claims. |
| 5 | Bounded agent runtime | Outbox/leases/budget enforcement; agent worker, registry and playground; real events, output, failures and cancellation. |
| 6 | Workflow definitions | Graph schema, DAG/mapping/branch validation, revisions and publication; backend tests precede graph UI. |
| 7 | Workflow runtime | Step scheduling, retries, branch merges, cancellation and recovery; restart/duplicate-delivery tests. |
| 8 | Flagship canvas | XYFlow palette/canvas/inspector, keyboard node list, save/validate/publish/run, responsive layouts connected to actual APIs. |
| 9 | Monitoring/history | Version-linked graphs, timeline, events, diagnostics, usage and linked retries; reconnection and empty/error states. |
| 10 | Product surfaces | Marketing, supported integration management, workspace settings and usage, consistent tokens and accessibility. |
| 11 | Release hardening | SSRF/authorization/redaction review, worker isolation, retention, migrations/restore rehearsal and production configuration. |

Future after MVP validation: schedules/webhooks, broader OAuth connectors, approval gates for consequential writes, multi-agent coordination, public template sharing, billing and sandboxed code. A curated template gallery follows the tool/install foundation. Evaluate Temporal only when durable timers or long-running approvals justify it.

No automated browser screenshot testing unless requested. Run meaningful backend tests, frontend TypeScript/ESLint and production build for implemented slices. Manual responsive/accessibility review remains required.
