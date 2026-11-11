# Guided creation for agents and workflows

## Intent

Make FlowForge usable by someone who understands their work but does not write code. The person should be able to start from a familiar task, configure only what that task needs, see what is missing, test with safe sample data, and publish a working agent or workflow. Provider setup, reusable skills, templates, tools and workflow nodes should feel like parts of that path.

## Current state

- The app supports five model providers, a verified model catalog, per-model capabilities and pricing profiles, and an Integrations screen that verifies keys and saves a workspace default.
- Agent drafts already have a guided editor with instruction, provider, input/output, tools, skills, memory, guardrails, readiness and test sections. Publication still depends on provider, model, schema and grant readiness.
- Workspaces have eleven starter skills and the skill model already supports editable drafts, examples, tool requirements and immutable versions.
- The built-in template catalog has thirteen agent/workflow starters by source inventory. Templates support preview, setup notes, sample input, independent drafts, import/export and sharing. Agent starters also exist in the front end, so some starter definitions are duplicated.
- The workflow graph supports twenty node types: manual, webhook, schedule and chat triggers; agent and LLM; approved local, HTTP and MCP tools; subworkflow, loop, approval, wait, condition, merge, transform, text, filter, JSON parse and result nodes.
- The landing page already shows an illustrative workflow, but some copy still describes execution capabilities as future work. The signed-in overview has a setup checklist, task start page and separate builder entry points.
- Provider adapter and API tests cover fixed hosts, credentials, model catalogs, publishing and completed runs. Those tests use controlled responses; there is no configured live provider credential or browser inspection session available in this audit. No specific provider failure could be reproduced from the current report.

## Goals

1. Give a first-time user one obvious start: choose a task or describe a goal, then use a recommended recipe.
2. Make each recipe explain its result, required setup, permissions, likely cost controls, sample input and next action before creation.
3. Let a user complete provider and tool setup without learning model IDs, JSON schemas, API contracts or MCP terminology. Keep an advanced path available.
4. Make agent templates and starter skills work together by copying editable skill drafts into the workspace, attaching them to the generated agent, and making each skill publish-ready before agent tests can reference its immutable version.
5. Keep provider selection, capability checks, saved defaults and run readiness consistent across Integrations, agent editing, templates and workflow LLM steps.
6. Expand the workflow toolbox only with tested, deterministic steps that solve common jobs without adding external dependencies.
7. Refresh public and in-app visual hierarchy using the existing Next.js/CSS/Lucide stack and accessible semantic controls.

## Non-goals

- Replacing the workflow graph engine or immutable agent/skill versioning.
- Adding provider families, OAuth, public hosting, billing, or a template marketplace.
- Requiring AI-generated configuration or a paid model call to choose a starter.
- Introducing arbitrary code execution or unreviewed external actions.
- Removing the direct agent editor, workflow canvas, JSON/schema advanced controls, or existing APIs.
- Claiming live provider acceptance without a real configured credential and a safe user-run integration check.

## Approaches considered

### 1. Guided recipe first — selected

Add a guided entry point to the existing workspace setup and template gallery. A recipe packages a task description, an agent or workflow definition, recommended starter skills, setup requirements, sample input and an expected result. The guided path checks workspace readiness, lets the user create the draft, links directly to missing setup, runs a sample, and then opens publication. The existing editors remain the place to inspect or customize the full definition.

This uses the existing provider, skill, agent, workflow, run and template modules. The main tradeoff is additional recipe metadata and orchestration in the template instantiation seam. Centralizing it there avoids a second execution model and keeps one source of truth for validation.

### 2. Improve each existing page separately

Simplify Integrations, agent editing, template browsing and workflow editing in isolation. This is a smaller first change, but it leaves users to discover cross-page dependencies and repeats setup guidance.

### 3. Replace the builders with one generated canvas

Create a new canvas that merges agent, workflow, provider and template configuration. This offers a unified visual model, but duplicates the graph/editor and version concepts already in use and creates a larger migration and accessibility risk.

## Proposed user experience

1. **Choose a goal:** the overview offers task categories and searchable recipes. A plain-language description may filter or recommend recipes without making a provider call.
2. **Review the recipe:** show what it will do, whether it creates an agent or workflow, the skills it uses, required connections/tools, sample input, result example, and whether an external action needs approval.
3. **Set up only what is needed:** for providers, guide the owner/admin through key verification and a runnable model. Hide setup-only models by default; expose them through an advanced choice with an explanation. Show provider-specific recovery for rejected keys, unavailable catalogs and missing model capabilities.
4. **Create a workspace draft:** template-created agents and workflows are workspace-visible under current access rules; do not describe these as private. Copy selected built-in skills as editable drafts and attach them to the agent. Since tests and publication pin published skill versions, guide the user to review and publish each copied skill before testing the agent, and re-run readiness after any skill edit. For workflow recipes, preserve current references and explain any required agent publication or service configuration before running.
5. **Preview or test with clear boundaries:** prefill the recipe sample and show readiness issues beside the relevant control. Use local preview for supported draft workflows; node-specific tests retain current confirmation and receipt restrictions. Durable full runs for workflows that include agents, LLMs, external services or pause steps require publication under current rules, so say this before the user publishes and display configured run caps and paid/external-call effects.
6. **Publish and continue:** show a short readiness summary and direct route to agent chat, workflow run history, deployment or trigger setup. Advanced editors remain accessible throughout.

## Workflow toolbox priorities

The runtime already has a broad set of node types, so add high-leverage operations rather than re-labeling existing work:

- **Switch:** route one value through named cases plus a default path, replacing chains of binary conditions for common status/priority routing. Before implementation, evolve the edge source-port contract compatibly: preserve existing `out`/`true`/`false` ports for old graph versions and condition nodes; give Switch cases stable IDs separate from editable labels; require exactly one default; define case deletion/rename behavior; and validate unknown case IDs before publication and preview. Keep case count bounded and make all outgoing paths visible and testable.
- **Remove duplicates:** produce a stable unique list using an optional field path, preserving first-seen order and bounded JSON size. This is deterministic and complements the existing list filter and For each steps.

Each node must be present in the API graph schema, graph validation, preview/test form, runtime, trace display, builder palette and starter templates. Unknown or invalid branches must fail validation before publication.

## Provider-flow investigation

The supplied request does not include a failing provider, model, UI step, response or trace. The existing automated suite passes, so there is no reproduced failure to patch safely. The implementation phase will add deterministic UI/model-selection coverage and inspect provider error propagation while preserving current credential isolation. If those checks expose a regression, fix it with a focused failing test. Live verification remains a manual step requiring the user's own provider credential; never place that credential in logs or test fixtures that reach version control.

## Visual direction

Use the `ui-ux-pro-max` recommendation for an AI-native SaaS product demo and feature layout, while retaining FlowForge's existing semantic colors, light surfaces, Lucide icon family and custom CSS system. Keep the public landing page focused on an accurate current product demo and simple start action. In the app, use progressive disclosure: task language first, technical labels and full configuration in the existing advanced surfaces. Form errors stay inline, keyboard focus stays visible, mobile layouts preserve readable canvas/list alternatives, and motion respects reduced-motion preferences.

## Constraints and acceptance

- Existing published agent/skill/workflow versions remain immutable; template use creates a new workspace-owned draft.
- Provider keys stay encrypted and are never returned or copied into recipes. A user-provided key is only used to verify a connection on the server.
- Permission, cost and side-effect policies remain server-authoritative. A UI recommendation cannot grant a tool or bypass publication checks.
- Workflow graph limits, task bounds, wait/approval rules, MCP/HTTP authorization and uncertain-outcome behavior remain unchanged.
- Automated tests prove recipe instantiation, workspace visibility language, skill copying/attachment/publication/edit readiness, provider/model readiness, supported draft preview versus publish-required durable runs, backward-compatible graph ports, and each new workflow node through the same interface used by the UI.
- Frontend checks include responsive layout, keyboard operation, meaningful empty/error states, typecheck, lint, API drift and production build.
- A manual GUI walkthrough covers first-time setup, a local-only workflow recipe, an agent recipe using a configured provider, and a workflow using each new node. Live provider acceptance requires the user's own credential.

## Builder calls

- Prefer static, reviewed recipes and local deterministic filtering over AI-generated setup. This avoids charging for discovery and keeps the first step useful without a provider connection.
- Keep beginner guidance in a single guided path; retain direct links to current builders and integrations for experienced users.
- Prioritize Switch and Remove duplicates because they fill distinct gaps in the existing condition/filter/loop toolbox without adding external side effects.
- Do not interpret “fix provider flows” as permission to guess at an unreported runtime failure. Add test coverage and repair only reproduced defects; document any remaining live-only checks.
- Skills copied from recipes are drafts; because agent tests consume published versions, the guided path must explicitly include review and publication before test, then surface re-publication when edits make the attached version stale.
- Call recipe-created resources workspace drafts, not private drafts, until the product implements access-controlled private visibility.
- Switch case identity uses stable IDs while labels remain editable. Legacy condition graph ports retain their current representation and behavior.
- Preserve the current split between local draft preview, node tests subject to confirmation/receipt checks, and durable published workflow runs. Recipe guidance must make the applicable path clear without weakening budget, receipt, or side-effect controls.
