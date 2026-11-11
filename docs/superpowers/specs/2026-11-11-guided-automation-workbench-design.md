# FlowForge Guided Automation Workbench Design

**Status:** Proposed for review

**Date:** 11 November 2026 (Asia/Karachi)

## Intent

FlowForge should help small teams turn recurring work into dependable AI automations. A user describes a task, shapes an agent or workflow with guided help, tests it against examples, publishes a bounded version, and improves it from execution evidence. The product's promise is not that AI will build an opaque automation correctly. It is that users can move from a task idea to a reviewable, controlled, observable automation without having to assemble infrastructure themselves.

The first experience should complete one useful job end to end: support-ticket triage that accepts a ticket, returns structured category and priority, routes to a human decision when needed, and exposes a trace of what happened. This carries forward the existing PRD's first use case. External write actions remain explicit, permissioned workflow steps and require the product's existing approval and receipt safeguards.

## Users and problem

The primary user is a developer, operations lead, automation freelancer, or small-team owner who knows a repeated process but may not know how to design an agent, map data, configure a trigger, or diagnose a failed model/tool call. They need to keep control over instructions, inputs, permissions, costs, and the decision to publish. Developers also need a stable way to invoke published versions from other applications.

Today, FlowForge has many of the underlying capabilities, but their breadth can make the first useful path hard to see. The workbench should make the next action obvious while preserving the workflow graph, agent configuration, and run evidence as editable, inspectable product objects.

## Product outcome and success

An invited pilot user can:

1. Describe a repeated task and receive a proposed agent/workflow setup grounded in configured models, tools, and templates.
2. Review and edit every generated instruction, schema, node, mapping, permission, and trigger before it is saved or published.
3. Run realistic examples, see validation feedback, and compare expected behavior with actual results.
4. Publish an immutable version, choose a manual or configured trigger, and see clear budget and approval controls.
5. Inspect each run's inputs, outputs, model/tool events, duration, measured or estimated cost, failure reason, and human feedback.
6. Use that evidence to change a draft and publish a new version without altering past runs.

Measure the first successful workflow, time to repair validation errors, completion/failure rate, run latency, usage reconciliation, and the number of runs that require operator intervention. Establish numeric targets from pilot observations; do not fabricate baselines or confidence scores.

## Goals

- Make one guided path join agent building, workflow composition, testing, publishing, triggers, and run learning.
- Keep AI-generated changes as proposals the user can inspect and edit.
- Keep published definitions immutable and executions reproducible from durable database state.
- Enforce workspace roles, tool grants, budgets, deadlines, data limits, and approval rules at the server/runtime layer.
- Preserve useful developer APIs and portable templates as parts of the same product.
- Keep local-first operation usable while clearly identifying what is not production-ready.

## Non-goals

- A general-purpose no-code business suite or a commitment to one industry.
- A marketplace, public hosting service, subscription billing, or compliance certification in this delivery.
- Unrestricted user code, arbitrary tenant URLs/processes, autonomous tool discovery, or unsupervised consequential writes.
- Hidden model reasoning, made-up quality scores, or automatic rewriting/publishing based only on feedback.
- Replacing the visual workflow graph with a chat-only automation format.

## Approaches considered

### Guided automation workbench (recommended)

Unify the user's journey around describing, configuring, testing, publishing, and learning from an automation. Keep agents and workflows distinct domain objects, with AI assistance generating reviewable drafts and the deterministic workflow runtime owning execution. This reuses the current code and gives the product a coherent reason to exist. It requires thoughtful onboarding and must make suggestions clearly provisional.

### Developer automation platform

Center the product on API contracts, hosted deployments, connectors, and reliability. This strengthens the embedding story, but leaves the existing builder and agent workbench capabilities as a collection of less-connected tools. Public hosting also requires operational work not included in the current local-release finish line.

### Packaged business automations

Center onboarding on a small catalog of complete recipes, starting with support triage. This makes initial setup concrete, but narrows positioning and creates a continuing burden to maintain vertical-specific connectors and templates. Keep recipes as the first-run path inside the recommended workbench rather than making them the entire product.

The recommended direction combines the guided workbench with one carefully supported starter journey. The first release remains local-first; hosted SaaS readiness is a later, separately gated phase.

## User experience and flow

### First-use journey

`Workspace overview -> Choose a task/template -> Describe the task -> Review agent and workflow draft -> Connect required provider/tools -> Try examples -> Validate -> Publish -> Configure trigger or deployment -> Monitor runs -> Review feedback -> Revise draft`

The Overview should emphasize a single next step for a new workspace and actual workspace activity for an established one. The guided setup can begin from the current agent/workflow workbench rather than a second visual editor. A user may start from the support triage recipe or an empty task description. The assistant should ask for missing business rules when they materially affect behavior; when information is not available, it must leave the field unset and label the assumption.

### Reviewable AI assistance

The assistant may draft instructions, simple input/output schemas, a suggested trigger, and an initial supported workflow graph from the user's description and the workspace's available capabilities. It must not invent tools, credentials, business policies, provider support, or success evidence. Generated fields are marked as suggestions until accepted. The user can inspect a change set, accept individual fields, edit them, or discard it. A generated graph must pass the same server validation as a hand-built graph.

### Testing and release

The user tests with saved examples and representative inputs. Failures point to an input path, node, permission, provider connection, or runtime event where available. Publishing is separate from saving and testing, creates an immutable version, and never starts execution by itself. Before activating a trigger or deployment, show the selected version, allowed actions, review requirements, limits, and external service charges that FlowForge cannot measure.

### Learning from executions

The run view is the operational record: state, initiating trigger, version, timeline, safe input/output display, model/tool calls, retries, approvals, costs and usage provenance, and final error. Users can give feedback and attach a note. Feedback can inform a future draft or evaluation example, but never changes a published version or triggers a model call without an explicit action.

## System design

### Existing platform to preserve

The repository is a Next.js App Router/TypeScript frontend and a FastAPI/Python modular monolith backed by PostgreSQL, Redis, and Celery. PostgreSQL is the durable source of truth; the queue carries identifiers and workers reload authorized state. Providers and tools are reached through bounded adapters. Credentials are encrypted server-side. Published agent/workflow versions are immutable. Existing local scope includes workspace accounts/roles, five provider families with a reviewed model set, agent authoring, bounded DAG workflows and subworkflows, durable runs/checkpoints/retries, approvals and timers, HTTP/MCP tools, schedules/webhooks, deployments, templates, usage controls, activity, and backup/restore rehearsal. Public hosting, billing, production operations, and some connector/OAuth capabilities remain explicitly incomplete.

The working tree contains extensive uncommitted changes for a redesigned agent workbench, assistant chat, workflow chat/LLM nodes, memory, skills, run traces/feedback, and overview. Treat these changes as existing user work: inspect and preserve them, reconcile their status and tests before adding overlapping functionality, and do not assume they are already validated or complete.

### Logical modules

- **Web workbench (Next.js):** task entry, agent/workflow authoring, generated-draft review, examples, publication, run monitor, and workspace navigation. Client state is for editing; server responses remain authoritative.
- **Identity and workspace policy (FastAPI):** membership, roles, ownership, CSRF, tool/credential grants, and request authorization.
- **Agent authoring and evaluation:** drafts, guided schemas, immutable versions, readiness checks, saved examples, and assistant suggestions.
- **Workflow authoring and validation:** graph persistence, typed node config, data mappings, version publication, and validation diagnostics.
- **Run admission and execution:** shared usage reservation/admission, idempotent submission, durable run state, checkpoints, worker claims, retries, cancellation, and safe replay.
- **Tools and provider adapters:** bounded model protocols, HTTP/MCP connectors, schema validation, allowlists, credential resolution, response limits, and event recording.
- **Triggers and delivery:** manual requests, webhook/cron/interval schedules, and hosted deployments linked to pinned versions.
- **Run evidence and feedback:** ordered events, safe traces, measured/estimated/uncertain usage, user feedback, and performance summaries.
- **Operations:** migrations, secret keys, backups, restore, readiness, logs/metrics, retention, and release procedures.

Keep the modular monolith. Do not introduce a new distributed service or workflow engine for the guided experience. The existing durable run engine already supplies the execution behavior and local seam.

### Deep-module and seam guidance

The product-level leverage should be a small guided path that lets a user prepare, validate, publish, and inspect an automation without each screen reproducing policy logic. The server-side application interface should expose task-level operations that return validated, reviewable draft data and normal run/version resources. The existing publication and run-admission modules remain the authoritative seams for policy, budgets, idempotency, and durable execution.

Builder assistance, manual editor actions, and templates are different sources of draft intent, but they should converge on the same agent/workflow draft contracts and validators. Do not create a second execution interface for assistants: assistant calls already use the normal budgeted run submission path. Do not expose internal memory, checkpoint, or provider protocol details to the frontend. Keep adapters for actual variation (provider/tool protocols and production/test implementations); avoid a generic plugin/automation framework with only one implementation.

Potential codebase-design work during implementation: identify repeated UI-level readiness/publish/run policy that has spread between agent and workflow surfaces; move authoritative behavior behind the existing server modules where possible; keep orchestration query helpers close to their owning domain. Only extract a shared workbench module if it can own a cohesive behavior behind a smaller interface and at least two real callers. Tests should cross that interface and assert observable output, authorization, and failure modes.

### Data and versioning

Use current workspace-scoped relational resources and migration discipline. The product journey relies on these durable records: workspace/membership; agent/workflow drafts; immutable versions and pinned references; examples/evaluation results; provider/tool connection references and grants; runs, events, checkpoints and step receipts; triggers/deployments; usage reservations/settlements; encrypted conversation turns; and feedback. Secrets and sensitive payloads remain encrypted or redacted. Store only hashes where a stable private conversation key is sufficient. Retention and deletion behavior must be explicit for conversation data and run payloads.

An AI suggestion is not a published object. Accepting a suggestion updates a draft under normal optimistic concurrency/revision rules. A run always resolves a pinned published version (or is an explicitly labeled editor test); deployment/trigger bindings point to an immutable version. Retries and replay obey operation-specific idempotency and unknown-outcome rules.

### Core interfaces and data flow

1. The frontend submits task context to a workspace-authorized assistant endpoint.
2. The server bounds and validates the request, selects an enabled provider/model, and starts the helper through ordinary run admission with the workspace budget and idempotency protections.
3. The assistant returns structured proposal data. The frontend shows a reviewable change set; user approval writes only to a draft through existing authoring contracts.
4. The server validates the draft graph, schemas, permissions, pinned versions, limits, and supported models. Validation identifies errors by resource and field.
5. An authorized publish request produces an immutable version. Trigger/deployment setup references the selected version and carries scoped credentials separately.
6. A manual, scheduled, webhook, chat, or hosted invocation creates/adopts a durable run record. Celery receives IDs, reloads current authorization/admission state, and executes bounded nodes using provider/tool adapters.
7. Each step commits state and safe event metadata. Outputs/checkpoints are encrypted where required. Unknown external outcomes are not automatically retried.
8. The run monitor reads durable status/events and renders actual evidence. Feedback is stored against a run/version and can seed examples only after an explicit user action.

Existing APIs and generated OpenAPI types remain the contract source. New operations should follow workspace scoping, CSRF on writes, idempotency keys for submissions, structured errors, bounded payloads, pagination, and regenerated frontend clients. Exact paths and schemas are implementation details for the builder unless a current contract needs migration.

### Security and safety

- Authorize every workspace operation and recheck permissions in asynchronous workers.
- Require explicit per-tool grants; deny write tools until the applicable approval and idempotency/receipt path is in place.
- Treat model output, user prompts, tool responses, template content, and generated graph data as untrusted.
- Enforce fixed HTTPS destinations and egress restrictions; deny private/internal addresses and tenant-supplied worker URLs.
- Keep provider/tool secrets out of prompts, event payloads, logs, and queue messages.
- Bound input/output sizes, model turns, tool calls, wall-clock time, spend, concurrency, loop expansion, response size, and retained conversation history.
- Make review gates visible and durable; a run parked for approval must not hold a worker.
- Distinguish measured usage, estimates, unknown/uncertain costs, and third-party charges.

## Delivery plan

### Phase 0: Reconcile current work

Reconcile and verify all current uncommitted work before adding any new feature. Map the changes to product surfaces, identify overlapping old/new implementations, inspect migrations and OpenAPI drift, and establish what actually passes. Preserve the user's working tree and resolve existing regressions or incomplete slices. Then finish the connected agent/workflow workbench, chat, skills, memory, run trace/feedback, and overview path as a coherent local experience. Update project status with verified facts only.

### Phase 1: One guided first-run task

Make a new workspace choose the support-triage task or a blank task. Guide the user to the required provider and tools; draft only supported, reviewable configuration; populate useful examples; and connect to existing validation, publication, and run monitor. Ensure every step has honest loading, empty, error, and recovery states. Do not add a parallel workflow representation.

### Phase 2: Close the learning loop

Connect run feedback and safe traces to saved examples and regression evaluation. Let users deliberately turn a failure or feedback item into an editable example, rerun a bounded evaluation, compare versions, and publish a new version only after explicit review. Track real operational measures without claiming causation or fabricated quality.

### Phase 3: Local release completeness

Reconcile UX/accessibility, role checks, pagination, error handling, retention, logs/metrics, restore rehearsal, migration checks, and documented local operating procedures. The completion target is a dependable local release that a pilot team can use with its own provider/tool credentials.

### Phase 4: Separate production-readiness decision

Before public multi-tenant SaaS, design and verify HTTPS/domain operations, capacity isolation, operator plan ceilings, key rotation, managed backups/retention, alerts/on-call, egress controls, privacy/deletion behavior, incident response, production email, real-account OAuth acceptance, and an external security review. Billing and public marketplace work follow evidence of pilot use and an explicit business decision.

## Acceptance criteria

- A new local workspace can complete the support-triage journey without reading developer documentation or using hidden setup steps.
- AI assistance cannot directly publish, activate a trigger, or perform a consequential write.
- The generated proposal uses only verified available models and configured tools; unsupported or missing facts are surfaced.
- The same server validation and publication checks apply to AI-generated and manually authored changes.
- Draft updates preserve revision/concurrency behavior, and published versions remain immutable.
- Runs share existing budget, authorization, idempotency, timeout, and durable-state enforcement.
- A user can inspect a completed or failed run and see its pinned version, actual persisted events, relevant tool/model evidence, and honest cost provenance.
- Feedback has no automatic effect. A user action is required to convert feedback/run evidence into an example or draft change.
- Cross-workspace access, role restrictions, tool revocation, duplicate delivery, worker restart, provider/tool timeout, cancellation, budget exhaustion, and unknown external write outcomes fail safely.
- The documented local release and restore path can be followed from the repository, and project status reflects only checks actually run.
- Public SaaS readiness is explicitly not claimed by meeting local acceptance criteria.

## Constraints and decisions

- Required stack remains Next.js App Router/TypeScript, FastAPI/Python, PostgreSQL, Redis/Celery, Docker Compose.
- Keep one deployable backend modular monolith for this phase.
- Existing local-first finish line is the initial release target; public hosting and billing are out of scope until operational prerequisites are designed and validated.
- The implementation plan must inspect current uncommitted work first and avoid discarding or silently replacing it.
- No quantitative adoption, reliability, or quality targets are invented; establish them through pilot observations.

## Left to the builder

- Exact screen copy, endpoint paths, schema field names, and migration numbers, provided existing contracts and user-visible behaviors are preserved.
- The smallest vertical slice sequence that reconciles existing changes without a broad rewrite.
- Whether code organization needs a new internal module after mapping current callers; any new external seam must have justified implementations/adapters.
- Numeric pilot thresholds after real usage establishes a baseline.
- Public hosting, pricing, billing, external integration priorities, and legal/privacy review remain future decisions rather than implicit commitments.

## Source documents

- `README.md`
- `docs/PRD.md`
- `docs/PROJECT_STATUS.md`
- `docs/DEVELOPMENT_PHASES.md`
- `docs/DEVELOPMENT_PROMPT.md`
- `docs/ARCHITECTURE.md`
- `docs/EXECUTION_MODEL.md`
- `docs/DESIGN.md`
- `docs/technical-architecture/`
