# Task 1 report

Implemented the shared pure launch model and accessible, request-free checklist.

## Behavior

- Local/agent journeys show save, check, sample, publish; durable runs publish before sampling.
- Current configuration, latest request and mode gate sample evidence; durable evidence additionally requires the matching published version and a clean current publication.
- Failed, waiting, running, cancelled and unknown attempts never complete the sample row. Unchecked/checking setup remains pending/working. Failed or invalidated setup cannot restore sample success.
- Setup-only configurations remain publishable while sample actions are blocked. Agent samples can describe unsaved submitted settings without weakening publication requirements.
- Viewer mutation buttons are disabled; existing result inspection remains available. Textual statuses, issue messages and warnings stay visible. Existing Button controls provide keyboard semantics; explicit focus styles and a 600px stacking breakpoint support keyboard and narrow screens.
- Deterministic configuration serialization sorts nested object keys while preserving array order and raw schema text.

## Files

- `frontend/src/features/launch/launch-model.ts`
- `frontend/src/features/launch/launch-model.test.ts`
- `frontend/src/features/launch/launch-checklist.tsx`
- `frontend/src/features/launch/launch-checklist.test.tsx`
- `frontend/src/app/globals.css` (appended checklist styles only)

## Verification

RED: `npm test -- src/features/launch` failed both suites because the new implementation modules did not exist, after tests were written first.

GREEN: Same focused command passed 2 files / 7 tests after implementation and again after formatting. `npm run typecheck` passed. `npx eslint src/features/launch` passed.

Tests exercise ordering, stale configuration/request/mode, superseding non-success states, matching publication versions and dirty publication, setup-only publication, unchecked/checking state, failed/rechecked evidence, unsaved agent evidence, deterministic serialization, no mount callbacks, status/warning rendering, named action callbacks, unknown target forwarding, viewer controls and result inspection.

## Self-review and concerns

Reviewed model against the exact shared contracts and baseline fixture. No persistence, requests, runtime validation rules or dependencies were added. Only owned files are staged.

Issue targets are opaque adapter metadata and are forwarded unchanged: editor adapters must resolve recognized targets and send unknown targets to general diagnostics. A shared component cannot recognize resource-specific graph node IDs or editor sections. Parent implementer was informed of this integration responsibility.

Narrow layout was verified by CSS inspection; no signed-in GUI or provider acceptance was performed in this isolated model/component task.
