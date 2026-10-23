# FlowForge AI — product design specification

Status: proposed design for approval, not an implemented application.

## Direction

Premium operational software: dark navy navigation, crisp white work areas, restrained indigo actions and purple agent accents. Prioritize graph readability, understandable permissions and honest execution feedback. Product voice: direct, calm, specific. Example headline: “Build agents. Connect work. Stay in control.”

References reviewed: all 12 root JPGs. References 1, 4, 7 and 10 inform palette/canvas/inspector composition; 2, 8 and 12 inform library hierarchy; 3, 6, 9 and 11 inform monitoring, branches and log inspection. Reference 5 informs typed auxiliary tool connections. These are structural inspiration; do not copy branding, model promises or research-oriented content.

## Design tokens

| Token | Value | Use |
|---|---|---|
| nav | #10182B | Sidebar and marketing hero |
| nav-raised | #1B2640 | Workspace switcher |
| page | #F6F8FC | Application background |
| surface | #FFFFFF | Cards, forms, inspector |
| text | #182238 | Primary content |
| muted | #59667C | Secondary content |
| border | #DFE5EF | Separators and inputs |
| primary | #4F46E5 | Main CTA, selected controls |
| primary-soft | #EEF2FF | Selection background |
| agent | #7C3AED | Agent icon and category |
| success | #15803D / #F0FDF4 | Completed state |
| warning | #92400E / #FFFBEB | Warnings and retries |
| danger | #B91C1C / #FEF2F2 | Failure and denied access |
| info | #0369A1 / #F0F9FF | Running and contextual help |

Typography: locally served Geist or Inter with system fallback; monospace for IDs, JSON and logs. Sizes: 12 metadata, 14 body, 16 section, 24 page title, 48–64 marketing headline. Line height 1.5 for body. Spacing scale 4/8/12/16/24/32/48/64px. Card radius 12px; input/button 8px; status pills 999px. Use 1px borders and subtle elevation, not heavy shadows. Icons: consistent 18–20px outline family. Verify text contrast in implementation; never encode status through color alone.

## Shared application shell

Desktop sidebar 224px, topbar 64px, normal content max-width 1440px with 32px gutters. Workspace switcher at top; Overview, Agents, Agent Builder, Workflows, Executions, Tools as primary navigation. Integrations, Usage, Settings below a divider. User menu and workspace role at foot. Active link uses indigo tint and a narrow accent line.

Topbar: breadcrumb, search/command control, help and account menu. Only display health information sourced from an actual health endpoint. Page headers have title, short purpose, and one dominant CTA. Breadcrumbs restore context when leaving a run for its originating definition.

## Screen inventory and connected routes

Routes below are under `/w/[workspaceId]` unless public.

| # | Screen and route | Composition and interactions |
|---|---|---|
| 1 | Marketing `/` | Navy header and hero; indigo CTA “Create your workspace”; secondary “Explore the builder”. Large illustrative workflow preview labeled “Example workflow”. Follow with agent-to-workflow walkthrough, safety controls, execution inspection, and final CTA. No invented customer logos, testimonials, uptime or pricing. |
| 2 | Authentication `/login`, `/register` | Split layout: focused white form and navy product story. Email/password, show-password button, validation and session-expired messages. Register creates workspace through onboarding. Forgot/reset password routes only become active when delivery is implemented. Preserve safe internal return URL. |
| 3 | Dashboard `/overview` | Workspace greeting, Create agent/Create workflow; live run counts, duration and measured usage; recent runs table; drafts needing attention. New workspace shows a three-step onboarding checklist instead of fake metrics. |
| 4 | Agents Library `/agents` | Search, status and tool filters; cards/table toggle; name, description, published version, permitted tools and last real run. Create, edit, duplicate, archive, test. Archive preserves referenced versions. |
| 5 | Agent Builder `/agents/new`, `/agents/[id]/edit` | Main configuration form plus compact summary. Tabs: Instructions, Model, Tools, Schemas, Limits. Name, description, provider/model capability, instructions, JSON schemas, permitted tools. Default proposal: 8 iterations, 60s deadline, $0.10 run cap. Save draft and Save version are distinct. Warn before leaving unsaved edits. |
| 6 | Playground `/agents/[id]/test` | Input JSON editor left; output and event trace right. Show immutable version, iteration count, tool permission outcomes, tokens and cost. Trace contains operational events and tool summaries, never private model reasoning. Run, cancel and copy output. Schema errors highlight JSON paths before submission. |
| 7 | Agent detail `/agents/[id]` | Overview, Versions, Runs tabs. Version timeline with author/time/change summary; read-only version inspection and diff; “Restore as new draft” preserves history. Link to workflows referencing this agent. |
| 8 | Workflow listing `/workflows` | Search, draft/published filter, list of name, node count, revision and last execution. Create blank or use a clearly labeled local example. Open editor and inspect version-specific runs. |
| 9 | Visual builder `/workflows/[id]/edit` | Flagship three-panel editor described below. Editable draft, immutable publication, validation, run input dialog and run monitor navigation. |
| 10 | Validation `/workflows/[id]/validation` | Also available as builder bottom panel. Errors grouped by node; code, message, field and repair action. Click selects node and inspector field. Show validated revision/hash. Publication blocked for stale or failing validation. |
| 11 | Execution monitor `/executions/[runId]` | Read-only graph with step overlays, timeline, event stream and selected-step input/output/logs. Header: state, version, elapsed time, cost/budget, cancel or retry. Clear reconnect banner when updates stop; retain last confirmed state. |
| 12 | Execution history `/executions` | Cursor-paginated table; status, definition, version, initiator, timestamps, duration and measured cost. Filter by date/agent/workflow/status. Failed row opens the failing step. Retry creates a new linked run. |
| 13 | Tool Registry `/tools` | Tool list with read/write class, schema, timeout, destination policy and availability. Detail exposes input/output schemas and allowed scopes. Secret reference is masked and never a secret value. Only owners/admins manage registry; others inspect according to role. |
| 14 | Integrations `/integrations` | MVP provider configuration and actual supported connection health only. Connected, credentials required, permission denied and unavailable states. Future OAuth connectors appear in a separate roadmap area without Connect buttons. No decorative Slack/Jira connections. |
| 15 | Workspace settings `/settings`, usage `/usage` | Settings tabs: General, Members, Security, Audit. Role-aware controls enforced by API. Usage shows date range, executions, tokens, reserved/settled cost, quotas and export only when supported. Limits show remaining allowance and reset time from API. |

Primary journey: landing → register → workspace onboarding → agent editor → test → save version → workflow list → builder → validate → publish → run → monitor → history. Existing user: login → overview → failed run → selected-step diagnostic → definition draft → validate → publish → new run.

## Flagship workflow builder

Desktop at 1440px: 64px collapsed product rail, 232px node palette, flexible canvas, 320px inspector. Builder takes full available height. The full sidebar returns outside editing mode.

```text
┌──────┬──────────────────────────────────────────────────────────────────────────┐
│ Logo │ Workflows / Support triage    Draft · Unsaved     Save Validate Publish Run│
├──────┼──────────────┬──────────────────────────────────────┬──────────────────────┤
│ Nav  │ Search nodes │ Editor · Runs                         │ Configure · Policies │
│      │              │                                      │                      │
│      │ TRIGGERS     │ [Manual input]──[Triage agent]         │ Triage agent         │
│      │ Manual input │                       │              │ Agent version v1     │
│      │              │                 [Priority route]     │ Input mappings       │
│      │ INTELLIGENCE │                  /            \      │ Output schema        │
│      │ Agent        │       [Format urgent] [Format normal] │ Permissions          │
│      │              │                  \            /      │ Timeout / retries    │
│      │ LOGIC        │                    [Result]          │                      │
│      │ Condition    │                                      │ $0.10 · 60s · 8 turns│
│      │ Transform    │ Zoom − + · Fit · Undo/Redo  Minimap   │                      │
├──────┴──────────────┴──────────────────────────────────────┴──────────────────────┤
│ Validation  1 error  1 warning    Events    Node output                           │
└──────────────────────────────────────────────────────────────────────────────────┘
```

Canvas: pale dotted background, white node cards, 1.5px curved edges and named ports. Trigger teal, agent purple, tool blue, condition amber, output slate; labels and icons reinforce types. Node header contains category icon, name and overflow. Body shows version/config summary, permission badge and budget. Selection has indigo outline. Runtime overlay includes icon/text plus duration; editor does not imply nodes have run.

Palette supports search, click-to-add and drag/drop. MVP enabled types: manual input, agent, approved tool, condition, safe field transform, result. Scheduled triggers, arbitrary code and webhook nodes are deferred. No unrestricted expression execution: use a bounded declarative mapping language.

Interactions: pan/zoom, fit, minimap, drag, connect typed ports, delete selected node with confirmation when connected, undo/redo, keyboard selection and inspector editing. Edges can be selected/deleted. Screen-reader-compatible node list offers equivalent add/connect/configure actions. Destructive keyboard actions never fire inside text fields. Dirty-state indication and save conflict recovery required.

Inspector tabs: Configuration, Input/output, Execution policy. Agent nodes pin version IDs. Tool nodes show exact permissions and destination allowlist. Condition nodes specify comparison and true/false branch. Input mapping uses source-node output field picker plus JSON preview. Retry controls expose attempts, backoff and whether the operation is safe to retry. Closing inspector restores canvas space.

Toolbar semantics: Save persists draft with optimistic concurrency; Validate checks server-side graph revision; Publish creates immutable version only after passing validation and authorization; Run executes a published version after input and budget review. No automatic execution on publish. Disabled actions explain missing requirements.

Validation examples: `MAPPING_REQUIRED` at `triage.input.ticket`; `CYCLE_DETECTED` with affected edge IDs; `TOOL_SCOPE_DENIED`; `MODEL_CAPABILITY_UNSUPPORTED`; warning `BUDGET_NEAR_MINIMUM`. Runtime diagnostics are separate: `PROVIDER_RATE_LIMITED`, attempt 2/3, retry in 4s; `TOOL_TIMEOUT`, 10s, no output; `BUDGET_EXCEEDED`, reserved cost would exceed $0.10. Provide correlation ID and safe corrective action, never raw credentials.

## Responsive behavior

≥1280px: full three-panel editor. 1024–1279px: collapsed nav and palette drawer, inspector 300px. 768–1023px: canvas primary, palette/inspector mutually exclusive drawers. Below 768px: bottom tabs for Steps, Canvas, Configure and Runs; accessible step list is default, configuration full width. Keep mobile editing available via list-based add/connect controls, and offer canvas pan/zoom. Toolbar moves secondary actions into labeled menu. Tables use responsive cards or contained horizontal scrolling; page itself does not overflow.

## Reusable components

AppShell, WorkspaceSwitcher, Breadcrumbs, PageHeader, Button variants, Input, Textarea, Select, Checkbox, Switch, Tooltip, Dialog, Sheet, Tabs, StatusBadge, PermissionBadge, BudgetMeter, MetricCard, FilterBar, DataTable, EmptyState, ErrorPanel, Skeleton, JsonEditor, SchemaFieldPicker, VersionTimeline, NodeCard, NodePalette, NodeInspector, ValidationList, RunTimeline and EventLog.

Use shadcn/ui primitives, Tailwind semantic tokens, React Hook Form/Zod for forms, TanStack Query for server state and XYFlow for graph interaction. Keep authorization and authoritative validation in FastAPI. Server Components handle route shell/initial reads; client components handle graph/forms/live monitor. Do not force a giant client application at the root.

## State and accessibility contract

Every data view: loading skeleton → content or actionable empty state → recoverable error. Empty library: “Create your first agent”; empty runs: “Runs appear after you execute a published version.” Server failure retains unsaved draft and offers retry. Offline editor blocks publish/run and labels local changes. Save conflict offers reload or copy draft; never silently overwrite.

Run states: queued, running, completed, failed, cancelled. Steps additionally show pending, retrying and skipped. Cancel request is labeled “Cancellation requested” until backend confirms. Success requires persisted completion. Example histories are visibly marked Sample data and never mixed into workspace metrics.

Keyboard focus visible, dialogs trap/restore focus, form errors announced and linked to inputs, touch controls ≥44px, reduced-motion preference respected. Status updates use polite live regions without announcing every token. JSON/log panes have wrap/copy controls and redact secrets server-side. Test 200% zoom and contrast before release.
