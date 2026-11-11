# Practical Workflow Nodes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task.

**Goal:** Add multi-case Switch routing and stable Remove duplicates processing across validation, preview, runtime, trace and builder UI.

**Architecture:** Keep graph schema version 1 and extend the source-port representation compatibly: legacy `out`, `true`, and `false` stay valid; switch ports use stable case IDs and the reserved `default` ID. Add deterministic operations through the existing `preview.run_preview` execution seam used by draft preview, node tests and durable runtime. Keep node definitions, execution outcomes and UI forms aligned through the existing graph seam.

**Tech Stack:** FastAPI/Pydantic/Python runtime and pytest; Next.js/TypeScript/@xyflow React/Vitest.

**Spec:** `docs/superpowers/specs/2026-11-11-noncoder-creation-experience-design.md`

## Global Constraints

- Each node must be present in the API graph schema, graph validation, preview/test form, runtime, trace display, builder palette and starter templates.
- Unknown or invalid branches must fail validation before publication and preview.
- Keep case count bounded and make all outgoing paths visible and testable.
- Switch case identity uses stable IDs while labels remain editable. Legacy condition graph ports retain their current representation and behavior.
- Workflow graph limits, task bounds, wait/approval rules, MCP/HTTP authorization and uncertain-outcome behavior remain unchanged.

## Review Focus

1. Existing stored condition graphs still parse and run with `true`/`false`; test backend and TypeScript graph fixtures.
2. Renaming/reordering a switch label retains its case ID and edge route; deleting a referenced case produces a blocking validation issue.
3. Default is unique and required; test missing/duplicate default and unknown outgoing IDs.
4. Switch values use strict JSON equality and select exactly one edge; test unmatched value and null.
5. Deduplication preserves first-seen order, supports a field path, and handles missing/null/type mismatch explicitly; test bounded behavior.

---

### Task 1: Graph contract and Switch validation

**Files:** `backend/app/modules/workflows/schemas.py`, `backend/app/modules/workflows/domain.py`, corresponding workflow schema/domain tests.

**Interfaces:** Add node type `switch`; config has `value: REFERENCE`, 1–8 `{id, label, value}` cases and exactly one implicit reserved default branch `default`. Edge `source_port` becomes a string bounded to 40 characters with validation by source-node type; preserve legacy port strings exactly. Case IDs match `[a-z][a-z0-9_-]{0,31}`, are unique and stable once created, and cannot equal `out`, `true`, `false`, or `default`. Case values are bounded JSON scalars (`string | number | boolean | null`) and must be unique under type-strict canonical JSON equality; labels are 1–40 characters. Validation requires exactly one outgoing edge for each case ID and one for `default`; condition nodes still require exactly one `true` and `false`; all outgoing edges from every other node use `out`, with the existing fan-out cardinality preserved. `list_deduplicate` config is defined in Task 2.

- [x] Add parse/validation tests for legacy condition edges, valid switch cases/default, malformed IDs, missing/duplicate/unknown ports, duplicate case values, node case limit, stable IDs and bounded references. The resumed implementer did not independently observe the earlier RED run; see task report.
- [x] Run focused tests; original implementer reported the intended RED phase, resumed implementer verified GREEN.
- [x] Implement schema and source-port validation; require exactly one outgoing edge for each case ID and `default`, prohibit `out`/`true`/`false` on switch nodes.
- [x] Run focused tests and ensure existing graph fixtures pass unchanged: 57 passed; full backend suite 406 passed; Ruff clean.
- [x] Commit `78be9cf`; independent task review approved with no findings.

### Task 2: Runtime and preview behavior for Switch and Remove duplicates

**Files:** `backend/app/modules/workflows/node_config.py`, `backend/app/modules/workflows/preview.py`, `backend/app/modules/workflows/node_test.py`, existing node-config/preview tests. Durable runtime calls `preview.run_preview`; change `runtime.py` only if a focused end-to-end test shows an additional type dispatch is required.

**Interfaces:** `switch` reads the configured `REFERENCE` (`{kind: input, pointer}` or `{kind: literal, value}`), returns the selected stable case ID as `selected_port`, and routes unmatched inputs through `default`. Add `list_deduplicate` with `source` input JSON Pointer and optional `item_pointer` into each object; output is `{items, count, removed}`; preserve first occurrence and array order, compare canonical JSON values strictly (so booleans differ from numbers), and fail on non-array input or a non-object item when `item_pointer` is set. If the selected item path is missing, keep each such item independently; explicit null is a value and repeated nulls collapse. With no `item_pointer`, compare each whole item. Bound input/output using existing JSON limits.

- [x] Write failing tests for matching/unmatched switch routing and deduplication equality, order, nested field, null, missing field, type errors and size limit.
- [x] Run tests and confirm failures: initial suite 30 intended failures; fix regressions 11 intended failures.
- [x] Implement runtime/preview dispatch using the same pure operation helper so preview and durable execution agree. Durable dispatch already shares `run_step`; no separate runtime edit was needed.
- [x] Verify trace includes selected switch port and deduplication output/count; focused suites pass. Task review's numeric equality finding was fixed and scoped re-review approved. Full backend suite: 447 passed; Ruff clean. Commits `48ec77b`, `7855895`.

### Task 3: Builder configuration, edges and trace display

**Files:** `frontend/src/features/workflows/workflow-builder.tsx`, `node-config-forms.tsx`, `node-config.ts`, `node-test-panel.tsx`, `frontend/src/features/executions/workflow-console.tsx`, graph edit/model files, `frontend/src/lib/api/generated.ts` (regenerate from OpenAPI), and adjacent Vitest suites.

**Interfaces:** Add Switch and Remove duplicates to the existing toolbox. Switch editor supports add/remove/reorder/edit labels and scalar values while preserving IDs; removing a case also removes only that case's edge and keeps the remaining case/default routes visible. Default route is always displayed. Graph edges serialize case IDs/default exactly. Remove duplicates exposes source and optional object field selector using current mapping controls. The canvas, node-test result and durable trace display the selected stable port; user labels are looked up from the node definition where available.

- [x] Add failing tests for ports, stable-ID label edits, removal validation, serialization and type-aware preview path messaging.
- [x] Run focused tests to confirm failures; initial editor/result tests failed before implementation, and insertion execution regressions reproduced RESULT_SKIPPED before the fix.
- [x] Implement forms, palette entries, output handles, labels and trace presentation. Switch insertion preserves single-active-branch continuation and all-join prerequisites through a Merge when needed.
- [x] Focused tests, typecheck, lint, OpenAPI drift checks and production build pass. Task review's Important finding was fixed and independently re-reviewed; commits `181be86`, `899ffb8`.

### Task 4: Starter recipes and end-to-end regression

**Files:** `backend/app/modules/templates/catalog.py` or existing starter modules, workflow template tests, frontend starter/workflow tests.

- [ ] Add one reviewed Switch routing template and one Remove duplicates cleanup template with sample input and expected result.
- [ ] Test structural validation, preview/runtime result, and compatibility with saved schema-version-1 condition templates.
- [ ] Run full relevant backend and frontend suites, typecheck, lint and API drift checks; commit.

