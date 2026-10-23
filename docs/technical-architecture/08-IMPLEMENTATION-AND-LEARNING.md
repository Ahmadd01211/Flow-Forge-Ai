# 08 — implementation slices and teaching plan

## How we will work together

Before each slice I will explain: the user behavior we are building, where the request/data travels, the rule being enforced and the test that will prove it. While coding I will explain new concepts at the file/function/transaction level when they appear, using a short concrete example rather than unrelated theory. Afterward I will show what changed, how it was checked, remaining limitations and the next dependency. We will keep a concise learning note with the slice so you can revisit it without rereading chat history.

This architecture step produces only documentation. After your approval we begin foundation, then complete one behavior at a time. We do not build a decorative 15-screen shell and call the runtime complete.

## Architecture concepts in plain language

| Concept | Meaning in FlowForge | Example |
|---|---|---|
| Control plane | Configuration and commands | Save an agent or ask to run a workflow |
| Execution plane | Workers doing bounded work | Call a model and an approved lookup tool |
| API contract | Agreement about request/response shape | POST run returns queued ID, not a made-up output |
| Schema | Allowed data shape | Ticket must be string; priority must be urgent/normal |
| Authorization | Whether this user may do this action on this resource | Viewer sees run status but cannot run or read raw ticket |
| Immutable version | Frozen configuration a run can reference later | Workflow v3 keeps using agent v2 after agent draft edits |
| Transaction | Related DB changes commit together or not at all | Run and outbox intent cannot be half-created |
| Outbox | Durable promise to send work later | API can accept run even if relay publishes a moment later |
| At-least-once delivery | A message may arrive repeatedly | Two copies must not create two active attempts |
| Idempotency | Repeated request/effect uses same logical identity | Double-click Run with same key returns same run |
| Lease | Temporary right to execute a step | Worker renews claim while alive |
| Fencing token | Newer claim invalidates old writer | Paused worker cannot overwrite recovered attempt's state |
| Checkpoint | Persisted completed progress | Successful lookup isn't repeated after worker restart |
| DAG | Directed graph with no cycles | Input → agent → condition → result terminates |
| Dependency resolution | Decide what may run next | A merge waits until each incoming branch is resolved |
| Budget reservation | Put a hold on spend before work | Two calls cannot both use last $0.05 |
| SSRF | Tool tricks server into calling forbidden destination | HTTP lookup must not reach cloud metadata/internal DB |
| Observability | Evidence about what happened and why | Correlated events show provider timeout on attempt 2 |

## First complete journey

An owner registers and creates a workspace. An editor creates a support-triage agent, tests an immutable snapshot, publishes a version, connects it to a manual-input workflow with a condition and result, validates/publishes, runs it, and sees persisted step output and usage. If the provider fails, the interface shows the real failure and remaining budget. External notifications are not needed for this first reliable journey.

## Small independently testable vertical slices

Each row includes a backend/API behavior and its smallest useful UI where applicable. Dependencies are explicit; independently testable means a slice has its own acceptance evidence, not that it can ignore prerequisites. Infrastructure foundation is the single enabling slice; later slices deliver observable product behavior. Do not write all models, all endpoints, then all screens in separate horizontal phases.

| Slice | Dependency | Deliverable and acceptance evidence | What I will teach at that step |
|---|---|---|---|
| S00 Foundation | Approval | New project-only repository; Next.js/FastAPI apps; Compose edge/DB/Redis/migrate; health page; frozen installs; CI typecheck/lint/build and backend health tests. No provider calls | Folder purpose, package/runtime, process vs container, request routing, env vs secret, why migrations exist |
| S01 Register/login/logout | S00 | Real password/session/CSRF endpoints and forms; session survives refresh, logout invalidates; rate/CSRF/expiry tests | Hash vs encryption, cookie flags, browser credentials, request validation and safe errors |
| S02 Create/select workspace | S01 | Owner membership and workspace switcher/onboarding; cross-workspace read denied; empty overview real | Ownership FK, membership authorization, server/client boundary and no-store reads |
| S03 Member roles | S02 | Add registered member/change/remove; role-aware settings; owner protections and two-user denial tests | Permission matrix, UI hints vs API enforcement, transaction lock for last owner |
| S04 Agent draft CRUD | S02 | Save/edit/list/duplicate/archive agent; form tabs for instructions/schemas/limits; revision conflict tests | DTO vs database model, RHF/Zod vs backend validation, optimistic concurrency |
| S05 Agent snapshots/history | S04 | Immutable test/published snapshots, detail/version diff/restore; immutability tests | Draft vs version vs API schema version, canonical hashes and reproducibility limits |
| S06 Provider connection/capabilities | S03,S05 | One selected real provider; encrypted admin credential entry, rotate/revoke, model metadata and safe errors; deterministic fake tests | Provider abstraction only at real boundary, capability differences, credential lifecycle and pricing estimates |
| S07 Run submission + deterministic agent test | S05,S06 | Idempotent queued run, budget reservation, outbox/maintenance and agent worker; playground shows real fake-adapter result labeled test; duplicate/dispatch-loss tests | Transactional outbox, broker vs ledger, logical idempotency and why 202 is not completion |
| S08 Live bounded agent generation | S07 | Provider generates validated structured result; checkpoints/events/tokens/cost shown; timeout and uncertain-acceptance tests, opt-in tiny real smoke test | Agent loop, model call boundaries, schema validation, known vs uncertain usage |
| S09 Cancellation/retry recovery | S08 | Stop/retry controls; worker killed at checkpoints; no unsafe replay; ledger holds/concurrency remain correct | State machines, leases/fencing, cancellation races, delivery vs domain retries |
| S10 Local Tool Registry and grants | S09 | Trusted bounded local tool with schemas; agent tool selection/invocation; denied generated call visible | Structured tool calling, least privilege, tool output as untrusted data |
| S11 Safe HTTP read tool | S10 | Fixed allowlisted API operation; permissions/limits/diagnostics; SSRF and redaction suite pass before enabling | URL vs destination policy, DNS rebinding, egress restrictions, idempotent reads |
| S12 Workflow draft + linear validation | S05,S10 | List/create/edit graph through simple accessible form; input→agent→result; DAG/type/ownership validation and revision tests | Nodes/edges/ports, graph vs layout, pure validation and typed mappings |
| S13 Branching semantics | S12 | Condition/transform/active merge definitions and validation; generated small-graph tests for activation and conflicts | Topological order, reachable paths, skipped vs failed, why merges wait |
| S14 Linear workflow execution | S09,S12 | Published linear workflow executes through separate pools, real persisted steps/events; restart and duplicate tests | Scheduler vs worker, dependency readiness, no blocking child task waits |
| S15 Branch execution and budgets | S13,S14 | Both branch paths, active merge, fail-fast/cancel/concurrency and shared run-budget evidence | Graph progress persistence, atomic readiness, parallel spend/permit races |
| S16 Canvas core | S12,S13 | XYFlow palette/connect/drag/inspect/save, undo/redo and accessible step list; dirty/conflict behavior verified | Canvas local state vs server state, client component boundary, reusable node UI |
| S17 Validate/publish/run from canvas | S15,S16 | Inline diagnostics select exact node/field; versioned publication/run input; stale validation blocked | Why frontend feedback isn't backend authority, pinning version references |
| S18 Monitor/history/usage | S17 | Read-only status graph, ordered events, step artifacts, filters, linked retries, measured budget view; reconnection/role tests | Poll cursor, result persistence, logs vs events vs artifacts, estimates vs final charge |
| S19 Product completion | S18 | Landing, actual integrations management, overview and settings polished against design; 15 connected responsive views, all state variants and keyboard review | Tokens/components/layout, progressive loading, accessibility and honest product claims |
| S20 Public-launch hardening | S19 | Email recovery/verification, TLS/secrets/egress configuration, migrations/backup restore, full security/recovery/CI gates and operator runbook | Threat modeling, deployment boundaries, migrations across releases, RPO/RTO and measured capacity |

S06 provider selection is a focused implementation decision based on available account, structured-tool capabilities, spend bounds and current official provider docs. We do not configure multiple providers or ask you for credentials during architecture review. You will enter credentials through a secure local setup path when that slice exists, never paste secrets into project documentation.

## Example walkthrough: what Save and Run actually do

**Save agent:** client form sends draft plus expected revision → router validates shape/session/CSRF → workspace policy checks editor role → agent service applies config rules → repository updates same revision inside transaction → API returns new revision → client updates saved state. You will see each file's contribution and the test for stale revision 409.

**Run workflow:** client submits immutable version/input with idempotency key → API validates authority/input/caps → transaction reserves budget and creates run/step/outbox → API returns queued ID → maintenance publishes task IDs → worker claims/checks/executes/persists → client polls ordered persisted events. We will trace one run ID through these stages rather than dumping every subsystem at once.

**Failure:** if a provider call starts and worker dies, database has “started” but no response. Replaying could charge twice. Reconciler fences old claim, marks unknown and fails precisely while preserving a spend hold. We will simulate this with a local fake server so the lesson and test cost nothing.

## Teaching and token discipline

- Keep PROJECT_STATUS.md as a short checkpoint: completed slice, verified checks, active issue, next step. Read it and the relevant module contract at the next turn; avoid reloading every document.
- Keep one authoritative design/contract; link rather than paste entire master requirements into each file or prompt.
- Update one small ADR when an important assumption changes, with trigger/evidence; routine implementation choices need a brief explanation, not repeated approval.
- Search scoped paths, read relevant files and inspect focused diffs. Do not scan unrelated folders or old projects.
- Explain a new idea when introduced, then refer back to its note. Do not repeat a whole distributed-systems lecture for each endpoint.
- Run checks matching the slice and broaden only for affected boundaries/new failures. Report actual evidence, never “should pass”.
- Use deterministic fixtures and no-cost fake providers for normal tests; live-provider checks are opt-in and bounded.
- You can ask for line-by-line explanation of any file. The default lesson covers purpose, request/data flow, key code decisions, failure cases and proof; we will teach the system as it becomes real.

## Approval gate

Please approve this technical package before S00. Approval starts foundation work only; each slice remains reviewable and testable, with clear explanations. No framework scaffold, package install, schema migration, infrastructure or provider connection was created during this architecture task.
