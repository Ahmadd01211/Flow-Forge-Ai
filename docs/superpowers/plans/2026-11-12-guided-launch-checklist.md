# Guided Launch Checklist Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development, preserving the user's selected execution method, to implement this plan task-by-task after review. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Connect existing recipe, setup, sample and publication controls through an accurate per-resource checklist.

**Architecture:** A pure frontend model and presentational checklist consume normalized state from the existing agent and workflow editors. Those editors retain all requests, authorization boundaries and execution controls. Sample evidence is scoped to the current session and submitted configuration.

**Tech Stack:** Existing Next.js/React/TypeScript, CSS tokens, Lucide and Vitest/Testing Library; existing FastAPI readiness/validation APIs.

**Spec:** `docs/superpowers/specs/2026-11-12-guided-launch-checklist-design.md` (approved by the user implementation request).

## Global Constraints

- No database migration, backend endpoint, localStorage progress record or new dependency in this slice.
- Tests remain optional for publication under existing policy.
- Publishing does not run anything.
- On reload, sample evidence resets to **Not tested in this session**; existing execution history remains available.
- Backend agent readiness and workflow validation remain the sources of configuration rules and permission checks.
- Preserve the current feature branch and user-local `.agents/` and generated `frontend/next-env.d.ts` changes.

## Review Focus

1. Local-only workflows must not acquire a provider prerequisite (Task 3).
2. External workflows must publish before sampling and retain cost/write/approval controls (Task 3).
3. Late responses, configuration edits and a later failed attempt must not restore stale success (Tasks 1–3).
4. Setup-only models, failed checks and changed dependencies must never imply runnable readiness (Tasks 1–2).
5. Viewers, blank drafts, unknown issue codes, restored versions and waiting approvals need truthful states (Tasks 1–4).

## File responsibilities and contracts

Create `frontend/src/features/launch/launch-model.ts` and adjacent test: pure state derivation. Create `launch-checklist.tsx` and adjacent test: accessible rendering. Integrate through existing `agents/agent-editor.tsx`, `agents/try-panel.tsx`, `workflows/workflow-builder.tsx`; keep API calls in their existing owners. Use adjacent tests and add `agents/agent-launch.test.tsx`. Update existing gallery/start-page tests, global CSS and manual checklist with the delivering task.

The model exports:

```ts
type LaunchAction = 'save' | 'check' | 'configure' | 'sample' | 'publish' | 'result';
type LaunchMode = 'agent_test' | 'local_preview' | 'published_run';
type LaunchIssue = { code: string; message: string; target?: string };
type SampleEvidence = {
  requestId: string; configKey: string; inputKey: string; mode: LaunchMode;
  state: 'running' | 'waiting' | 'completed' | 'failed' | 'cancelled' | 'unknown';
  runId?: string; versionId?: string;
};
type LaunchFacts = {
  mode: LaunchMode; saved: boolean; dirty: boolean; canEdit: boolean;
  configKey: string; latestRequestId: string | null;
  check: 'unchecked' | 'checking' | 'failed' | 'blocked' | 'passed' | 'setup_only';
  issues: LaunchIssue[]; warnings: LaunchIssue[];
  publishedCurrent: boolean; publishedVersionId: string | null;
  sample: SampleEvidence | null;
};
type LaunchStep = {
  id: 'save' | 'check' | 'sample' | 'publish'; title: string;
  status: 'pending' | 'working' | 'blocked' | 'complete'; description: string;
  action: LaunchAction | null;
};
function launchConfigKey(value: unknown): string;
function deriveLaunchSteps(facts: LaunchFacts): LaunchStep[];
```

`launchConfigKey` deterministically serializes JSON object keys in sorted order, preserves array order, and remains in memory. It is an equality key, not a security hash. Editor adapters pass the actual submitted definition including schemas; invalid raw schema text participates in the key until corrected. Never include provider secrets or run output. `inputKey` identifies the submitted input for metadata only.

Use this baseline test fixture, then override fields for each case:

```ts
const readyFacts: LaunchFacts = {
  mode: 'agent_test', saved: true, dirty: false, canEdit: true,
  configKey: 'current', latestRequestId: null, check: 'passed',
  issues: [], warnings: [], publishedCurrent: false,
  publishedVersionId: null, sample: null,
};
```

Adapters choose `blocked` when server errors exist; `setup_only` is exclusively publishable-but-unrunnable. Preserve the existing permission to test unsaved agent settings. On a hidden-to-visible tab transition, clear active checklist sample evidence and mark setup unchecked; leave existing outputs/history intact. This is conservative invalidation, not a claim of detecting external changes.

### Task 1: Pure checklist model and accessible component

**Files:** Create `frontend/src/features/launch/{launch-model.ts,launch-model.test.ts,launch-checklist.tsx,launch-checklist.test.tsx}`; modify `frontend/src/app/globals.css` only for checklist styles.

**Interfaces:** Produce the model above and `LaunchChecklist({ steps, issues, warnings, canEdit, onAction, onIssue }: { steps: LaunchStep[]; issues: LaunchIssue[]; warnings: LaunchIssue[]; canEdit: boolean; onAction: (action: LaunchAction) => void; onIssue: (issue: LaunchIssue) => void })`.

- [x] Write failing tests with a complete clean saved fixture named `readyFacts`: `expect(deriveLaunchSteps({...readyFacts,mode:'local_preview'}).map(s=>s.id)).toEqual(['save','check','sample','publish'])`; published-run mode equals `['save','check','publish','sample']`.
- [x] Add assertions that mismatched `configKey` or `latestRequestId` never completes sample; matching `completed` does; later `failed`, `waiting` and `unknown` do not. Published-run completion additionally requires matching version ID and clean current publication. `setup_only` blocks sample while preserving publish availability. Viewers receive disabled mutation actions; render every status text and warnings.
- [x] Run from `frontend`: `npm test -- src/features/launch`; confirm failures are missing behavior, then implement model/component. Pending check does not imply failure; issue actions with unknown targets fall back to general diagnostics. No automatic calls on mount.
- [x] Repeat focused tests; verify keyboard action names, narrow stacked styles and preserved warnings. Commit the focused deliverable.

### Task 2: Agent setup and sample evidence

**Files:** Modify `frontend/src/features/agents/{agent-editor.tsx,try-panel.tsx}`; create `agent-launch.test.tsx`; extend `launch-model.test.ts` only for model gaps.

**Interfaces:** Consume Task 1 contracts. Extend `TryPanel` with optional `onSampleEvent?: (evidence: SampleEvidence) => void` and `configKey?: string`; use the supplied key or `launchConfigKey(config)` when absent. Capture key/input/request ID at submission, emit running synchronously then observed terminal/pending state. Existing callers work unchanged. Parent updates latest request only on submission and ignores stale terminal callbacks.

- [x] Write rendered editor tests: unsaved agent -> Save; selected provider missing -> existing model/Integrations control; unpublished attached skill -> existing skills controls; unknown server issue -> general publish diagnostics. Assert `expect(mockTry).not.toHaveBeenCalled()` after checklist navigation/setup checks.
- [x] Cover unsaved configuration submitted to TryPanel, edit while pending, two out-of-order attempts, latest failure after earlier success, setup-only model, failed readiness fetch and viewer restrictions. Assert stale completion never renders **Sample succeeded**. A hidden-to-visible transition clears completion while retaining historical output, and a subsequent setup check alone does not reinstate sample success.
- [x] Run `npm test -- src/features/agents/agent-launch.test.tsx` and observe RED. Implement adapters using existing `ReadinessRead`, `SECTION_BLOCK` and `reveal`, sharing the readiness request with the publish dialog. On tab return mark setup unchecked; explicit check fetches saved readiness. Dirty configuration requires user save first. Scope requests so late readiness cannot apply to another revision.
- [x] Run focused tests plus existing agent model/schema tests and `npm run typecheck`; verify no change to `/try` payload, budget/approval behavior or publication eligibility. Commit.

### Task 3: Workflow preview, publication and full-run checklist

**Files:** Modify `frontend/src/features/workflows/workflow-builder.tsx`; extend `workflow-builder.test.tsx` and `selected-path.test.tsx` where needed.

**Interfaces:** Consume Task 1 contracts; use existing `Validation` and `requiresPublishedRun(graph.nodes, workflowOptions)`. Bind symbolic actions to existing save/validate/input/publish/result controls. Capture submitted graph key, request ID and (for durable runs) published version ID before each request.

- [x] Add tests for Remove duplicate contacts with no provider: successful local preview completes only **Try a sample**, never publication or durable execution. Assert no workflow-run POST occurs.
- [x] Add external-workflow test: row order is save/check/publish/sample; opening the sample controls does not call a model or write tool. A saved published version is required by the existing Run control. Pending approval/wait and polling expiry do not show success; completed matching version does.
- [x] Cover edit-during-preview/run, old validation response, failed save during save-and-check, a changed publication, hidden-to-visible invalidation, viewer access, and unknown node issue target. Assert no stale green state and reveal the selected node or diagnostics fallback.
- [x] Run `npm test -- src/features/workflows/workflow-builder.test.tsx src/features/workflows/selected-path.test.tsx` to observe RED; integrate without changing graph validation, join behavior or runtime requests. Render checklist in the existing editor rather than restructuring the large builder.
- [x] Repeat tests and `npm run typecheck`; assert existing Switch insertion/continuation and stable-port tests remain green. Commit.

### Task 4: Recipe handoff, manual acceptance and integrated verification

**Files:** Modify `frontend/src/features/templates/{template-gallery.tsx,template-gallery.test.tsx}`, `frontend/src/features/workspace/{task-start.tsx,task-start.test.ts}`, `docs/manual-testing/noncoder-creation.md`, `docs/PROJECT_STATUS.md`.

**Interfaces:** Existing resource editor routes remain unchanged. Gallery success action uses **Continue setup** and links to the created resource. Retain copied-skill links and exactly one draft creation action.

- [x] Add failing gallery/start tests for agent/workflow handoff, preservation of skill publication links and no second instantiate POST; links resolve to existing routes. Cover imported recipes without sample input with instructions to enter a sample, not invented data.
- [x] Run the focused suites, implement handoff copy, and repeat them. Document session-scoped sample evidence, post-edit rechecks, external workflow publication order and explicit paid/external runs.
- [x] From `frontend`, run `npm test`, `npm run typecheck`, `npm run lint`, `npm run api:check`, then `npm run build` sequentially. All must exit zero; preserve incidental generated-file differences. No backend suite repeat is needed unless backend behavior or contracts change.
- [x] Check the manual journey for one agent, the deduplication recipe and one external workflow; record automated checks separately from the user's signed-in GUI/live-provider acceptance. Commit the deliverable.

## Completion

Implementation is complete when every task is checked, checklist tests cover all five review-focus cases, current verification passes, and one final combined review has no unresolved blocking findings. The shared model owns checklist semantics; existing services own readiness/execution truth. The user authorized implementation after receiving this plan; execution retained the selected subagent-driven method.


## Delivery evidence (13 November 2026)

Tasks 1-4 and their reviews are complete. Key commits: 69a38c1 (shared model), e3a8f19/46d37d1 (agent adapter), 011d0ba/afec66a (workflow adapter), c0b4d57 (recipe handoff), and b4b6827 (final review fixes). Connector usability changes are in 5b80660, 9c44825 and e147913.

Final frontend verification: 169 tests across 32 files, typecheck, lint, API consistency and production build passed. The final scoped review approved all four findings; no blocking findings remain. Manual guide actions/routes were source-checked; signed-in GUI and real-provider/API/MCP acceptance remain unchecked for the user. Local runtime smoke returned readiness ready and homepage HTTP 200. No backend contracts changed, so backend suites were not repeated.
