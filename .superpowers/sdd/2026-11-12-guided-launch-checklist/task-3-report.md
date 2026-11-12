# Task 3 report: workflow launch checklist

Status: implemented and scoped verification passed.

## Delivered

- Added the shared four-row launch checklist inside the existing workflow editor. Local rows remain save/check/sample/publish; workflows classified by existing `requiresPublishedRun` use save/check/publish/sample.
- Explicit setup checks use the existing save-and-validate flow. Failed saving stops validation. Live draft checks continue unchanged and cannot supply checklist completion. Submitted configuration identity and a generation counter reject validation/publication responses after intervening edits, including edit then undo.
- Sample/result actions open and focus existing input/result controls; they do not run anything. Existing Preview/Run controls and request payloads remain responsible for execution. Preview evidence remains local; durable evidence captures the published version and only completed matching runs succeed. Waiting, failures, cancellation and polling expiry remain non-success states.
- Session evidence resets after edits and hidden-to-visible tab transitions. Late sample responses are rejected by request identity/configuration identity. Publishing another version invalidates durable sample matching.
- Issue actions select and reveal a known node in Steps view using the existing inspector selection helper. Unknown node targets focus the diagnostics fallback.
- Added optional `canEdit` to the builder, disabled workflow mutation toolbar/checklist actions for viewers, guarded request handlers, and supplied workspace role from the edit server page using the existing session API pattern. Backend authorization remains authoritative.
- Refined shared checklist with native accessible details: all titles and textual statuses stay visible; only the next incomplete actionable step opens initially. Other descriptions/actions remain available through disclosure. Warnings and issue actions remain visible. Added only checklist-scoped CSS using existing semantic tokens.
- Clarified palette guidance: selecting a step and clicking a node adds a connected step without dragging. Existing Switch insertion test still saves the exact backend executable continuation fixture and now exercises the saved graph through existing check/preview controls.

## Verification

Meaningful initial RED: added workflow checklist integration test failed because the Launch checklist region did not exist; the existing eight workflow/selected-path tests passed. Implemented the adapter and observed GREEN. Additional regression tests exposed fixture/query problems which were corrected before final verification.

Final focused command (from frontend):

`npm test -- src/features/workflows/workflow-builder.test.tsx src/features/workflows/selected-path.test.tsx src/features/launch/launch-checklist.test.tsx src/features/launch/launch-model.test.ts src/features/agents/agent-launch.test.tsx --maxWorkers=2`

Result: five files, 41 tests passed. Includes 15 workflow-builder tests, existing stable-port/continuation coverage, shared model/checklist coverage, and all 15 agent launch regressions.

Coverage includes local Remove duplicate contacts preview without provider or workflow-run POST; sample disclosure without execution; external ordering/publication requirement; waiting and matching completion; changed publication; polling expiry; edits during preview/run; late validation after edit/undo; failed save-and-check; hidden-to-visible invalidation; viewers; known-node reveal and unknown-node diagnostics fallback.

`npm run typecheck`: passed.

Scoped ESLint for workflow builder/tests, shared checklist/tests and workflow edit server page: passed.

`git diff --check`: passed before final formatting (no whitespace problems introduced by formatting).

## Boundaries and handoff

No graph validation, join logic, classifier, runtime endpoint/request payload, dependency, backend, migration or persistent progress record changes. Publication still does not run anything. Existing execution history remains available.

Tests use existing frontend API mocks and the backend continuation fixture; this slice did not execute a live backend preview or browser visual QA. Controller owns final integrated suite/build/lint/API checks after Task 4. No full suite/build/lint/API command was run.

Task 4 can extend the workflow edit server page to pass optional recipe metadata. No connector files, `.agents/`, or generated `frontend/next-env.d.ts` were edited/staged by this task. Those pre-existing local changes remain untouched.

No known implementation blocker remains in this slice.

## Review round 1 fixes

Addressed both findings in `task-3-review-report.md`.

P2: Preview now captures request identity and configuration generation before awaiting a dirty save. After save, it checks generation, configuration key and latest request identity before sending the existing preview POST. Intervening edits (including edit then undo), visibility invalidation or superseding requests stop that preview; completion retains the existing request/key guard. Failed saving clears the preallocated sample identity rather than leaving an unexecuted attempt running. Preview request endpoint, input and expected_revision payload semantics are unchanged.

Added a deferred-PATCH regression: create dirty A, start Preview, edit to B and undo to A while saving is pending, resolve save, then check setup. It asserts no Sample succeeded, Not tested in this session, and zero preview POSTs. Meaningful RED observed before the fix: workflow-builder suite had 1 failed and 16 passed; the failure showed a Sample succeeded paragraph where null was expected.

P3: Replaced the replacement character in the shared checking description with ASCII `Checking setup...`. Added an explicit pending-validation test asserting this visible description before resolving validation.

Final focused verification (from frontend):

`npm test -- src/features/workflows/workflow-builder.test.tsx src/features/workflows/selected-path.test.tsx src/features/launch/launch-model.test.ts src/features/launch/launch-checklist.test.tsx src/features/agents/agent-launch.test.tsx --maxWorkers=2`

Exact summary output:

```text
Test Files  5 passed (5)
     Tests  43 passed (43)
```

`npm run typecheck` passed (tsc --noEmit, exit 0).

`npx eslint src/features/workflows/workflow-builder.tsx src/features/workflows/workflow-builder.test.tsx src/features/launch/launch-model.ts` passed (no diagnostics, exit 0).

`git diff --check` passed. No full suite/build/lint/API run. No protected files staged or changed by this round.
