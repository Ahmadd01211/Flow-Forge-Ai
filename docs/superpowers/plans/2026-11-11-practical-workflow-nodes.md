# Practical Workflow Nodes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task.

**Goal:** Add multi-case Switch routing and stable Remove duplicates processing across validation, preview, runtime, trace and builder UI.

**Architecture:** Keep graph schema version 1 and extend the source-port representation compatibly: legacy `out`, `true`, and `false` stay valid; switch ports use stable case IDs and a reserved default ID. Add deterministic operations through existing workflow node dispatch. Keep node definitions, execution outcomes and UI forms aligned through the existing graph seam.

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

**Interfaces:** Add node type `switch`; config has `value` source reference, up to 8 `{id, label, value}` cases and exactly one implicit reserved default branch `default`. Edge `source_port` becomes a bounded string with validation by source-node type; preserve legacy port strings exactly. Case IDs match `[a-z][a-z0-9_-]{0,31}` and are stable once created. Case values are bounded JSON scalars (`string | number | boolean | null`); labels are 1–40 characters. `list_deduplicate` config is defined in Task 2.

- [ ] Add failing parse/validation tests for legacy condition edges, valid switch cases/default, malformed IDs, missing/duplicate/unknown ports, duplicate case values and node case limit.
- [ ] Run focused tests and confirm intended failures.
- [ ] Implement schema and source-port validation; require exactly one outgoing edge for each case ID and `default`, prohibit `out`/`true`/`false` on switch nodes.
- [ ] Run focused tests and ensure existing graph fixtures pass unchanged.
- [ ] Commit.

### Task 2: Runtime and preview behavior for Switch and Remove duplicates

**Files:** `backend/app/modules/workflows/runtime.py`, `backend/app/modules/workflows/preview.py`, `backend/app/modules/workflows/node_test.py`, existing runtime/preview test modules.

**Interfaces:** `switch` reads a configured input/literal source using established expression conventions, returns the selected stable case ID as `selected_port`, and routes unmatched inputs through `default`. Add `list_deduplicate` with `source` JSON pointer and optional `field` JSON pointer; output is `{items, count, removed}`; preserve first occurrence and array order, compare canonical JSON values strictly, and fail on non-array input or a non-object item when a field path is requested. Bound output by existing JSON/task limits.

- [ ] Write failing tests for matching/unmatched switch routing and deduplication equality, order, nested field, null, missing field, type errors and size limit.
- [ ] Run tests and confirm failures.
- [ ] Implement runtime/preview dispatch using the same pure operation helper so preview and durable execution agree.
- [ ] Verify trace includes selected switch port and deduplication output/count; run focused tests and commit.

### Task 3: Builder configuration, edges and trace display

**Files:** `frontend/src/features/workflows/workflow-builder.tsx`, `node-config-forms.tsx`, `node-config.ts`, `node-test-panel.tsx`, graph edit/model files and adjacent Vitest suites.

**Interfaces:** Add Switch and Remove duplicates to the existing toolbox. Switch editor supports add/remove/reorder/edit labels and scalar values while preserving IDs; default route is always displayed. Graph edges serialize case IDs/default exactly. Remove duplicates exposes source and optional object field selector using current mapping controls. Builder and trace render labels by stable case ID and display execution-selected routes.

- [ ] Add failing tests for ports, stable-ID label edits, removal validation, serialization and type-aware preview path messaging.
- [ ] Run focused tests to confirm failures.
- [ ] Implement forms, palette entries, output handles, labels and trace presentation.
- [ ] Run focused tests, typecheck, lint and API drift checks; commit.

### Task 4: Starter recipes and end-to-end regression

**Files:** `backend/app/modules/templates/catalog.py` or existing starter modules, workflow template tests, frontend starter/workflow tests.

- [ ] Add one reviewed Switch routing template and one Remove duplicates cleanup template with sample input and expected result.
- [ ] Test structural validation, preview/runtime result, and compatibility with saved schema-version-1 condition templates.
- [ ] Run full relevant backend and frontend suites, typecheck, lint and API drift checks; commit.

