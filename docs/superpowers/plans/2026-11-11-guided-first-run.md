# Guided First Run Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give a new FlowForge workspace a clear way to start with support-ticket triage or choose a blank agent/workflow, then carry the user into the existing editable, testable authoring flow.

**Architecture:** Add a small workspace task-selection page and link to it from the existing setup view. Reuse the support-triage template and current template preview/instantiation APIs; keep task-to-route selection in a pure frontend module that can be tested without rendering the application. The current workflow graph, validation, publication, run, and trace modules remain authoritative.

**Tech Stack:** Next.js App Router, React, TypeScript, Vitest, existing FastAPI template endpoints, PostgreSQL-backed immutable versions and durable runs.

**Spec:** `docs/superpowers/specs/2026-11-11-guided-automation-workbench-design.md` (Phase 1: One guided first-run task)

## Global Constraints

- Keep the existing Next.js App Router/TypeScript frontend and FastAPI/Python modular monolith.
- Do not create a second workflow editor or execution interface.
- AI-generated fields remain suggestions and may not publish, activate triggers, or perform consequential writes.
- Use only existing reviewed templates, providers, and configured tools; do not invent credentials, policy, or evidence.
- Existing authorization, draft revision, validation, publication, budget, and run interfaces remain authoritative.
- Public hosting and billing remain out of scope.

## Review Focus

- A viewer can see the starting page but cannot create or instantiate a draft; the existing `canCreate` restriction remains effective.
- A workspace ID is preserved in every selected destination; starting links never escape the workspace route.
- An unknown or unavailable `focus` query does not hide templates or prevent normal gallery use.
- A missing provider connection is explained before the user tries to publish or run the template.
- The setup checklist and task picker remain usable on narrow screens and with keyboard navigation.

---

### Task 1: Model guided starting choices

**Files:**
- Create: `frontend/src/features/workspace/task-start-model.ts`
- Create: `frontend/src/features/workspace/task-start-model.test.ts`

**Interfaces:**
- Produces `startingChoices(base: string)` returning the stable choices `support-triage`, `blank-agent`, and `blank-workflow`, with title, description, and workspace-relative `href` for each.
- Produces `prioritizeTemplate<T extends { key: string }>(items: T[], focus?: string): T[]`; it moves the focused key to the front when present, preserves relative order for all other items, and returns the original order when the focus is missing or unknown.

- [x] **Step 1: Write failing tests**

Test that the choices route support triage to `${base}/templates?focus=support-triage`, blank agent to `${base}/agents/new`, and blank workflow to `${base}/workflows`. Test that prioritization moves only the matching item and leaves the list unchanged for missing/unknown focus.

- [x] **Step 2: Run the focused tests and verify the expected missing-module failure**

Run from `frontend`: `npm run test -- src/features/workspace/task-start-model.test.ts`

- [x] **Step 3: Implement the two pure functions**

Keep the module free of React, network calls, and workspace state so the interface is cheap to test.

- [x] **Step 4: Re-run focused tests and verify they pass**

Run from `frontend`: `npm run test -- src/features/workspace/task-start-model.test.ts`

- [x] **Step 5: Commit the task**

### Task 2: Add the workspace task-selection page

**Files:**
- Create: `frontend/src/app/w/[workspaceId]/start/page.tsx`
- Create: `frontend/src/features/workspace/task-start.tsx`
- Create: `frontend/src/features/workspace/task-start.test.ts`
- Modify: `frontend/src/app/w/[workspaceId]/overview/page.tsx`
- Modify: `frontend/src/app/globals.css`
- Create: `frontend/vitest.config.mts`
- Test: `frontend/src/features/workspace/task-start-model.test.ts`

**Interfaces:**
- Consumes `startingChoices(base)` from Task 1.
- Produces a server-rendered, keyboard-navigable page with three links: recommended support-ticket triage, blank agent, and blank workflow.

- [x] **Step 1: Write a failing server-rendered component test**

Render `TaskStart` with a workspace ID and assert it produces the page heading and the three expected anchor destinations. Use `react-dom/server` with the real component; do not snapshot the entire markup.

- [x] **Step 2: Run the focused test and verify the expected missing-component failure**

- [x] **Step 3: Add the page and component**

Use semantic links and existing `PageHeader`, `Button`, and panel styles. Configure Vitest in an ESM TypeScript config to resolve the same `@/` source alias as the app so the real server-rendered component test runs without a config-loader warning. Replace the setup hero's generic workflow CTA with a clear “Choose a task” link to `${base}/start`; retain the detailed setup checklist.

- [x] **Step 4: Run both focused tests, lint, and typecheck**

Run from `frontend`: `npm run test -- src/features/workspace/task-start-model.test.ts src/features/workspace/task-start.test.ts`, `npm run lint`, and `npm run typecheck`.

- [x] **Step 5: Commit the task**

### Task 3: Focus the support-triage starter in the existing gallery

**Files:**
- Modify: `frontend/src/app/w/[workspaceId]/templates/page.tsx`
- Modify: `frontend/src/features/templates/template-gallery.tsx`
- Modify: `frontend/src/features/workspace/task-start-model.ts`
- Modify: `frontend/src/features/workspace/task-start-model.test.ts`

**Interfaces:**
- Consumes `prioritizeTemplate(items, focus)` from Task 1.
- The templates page reads the `focus` search parameter and passes it to the gallery.
- The gallery puts a matching available starter first and marks it as recommended. Existing preview and instantiate actions remain unchanged.

- [ ] **Step 1: Add failing focused-template tests**

Cover matching, unknown, and absent focus. Verify unmatched templates keep their relative order.

- [ ] **Step 2: Run the focused tests and verify the expected failure**

- [ ] **Step 3: Implement search-parameter pass-through and recommendation treatment**

Keep the deep link presentation-only. Do not instantiate or mutate anything until the user selects the existing “Use template” action.

- [ ] **Step 4: Re-run focused tests, lint, and typecheck**

- [ ] **Step 5: Commit the task**

### Task 4: Add the manual first-run test guide

**Files:**
- Create: `docs/learning/24-GUIDED-FIRST-RUN.md`
- Modify: `README.md`

**Interfaces:**
- Produces a short manual checklist that names the page, action, expected result, and recovery route for each step.
- Documents the local app URL, account/workspace setup, where to connect a provider, and that a provider call can incur charges.

- [ ] **Step 1: Write the guide against the implemented routes and controls**

Cover support triage preview, instantiate, edit, connect a provider, test the sample input, validate, publish, run, inspect trace, and create a blank agent/workflow. State explicitly which steps require a provider key and which trigger configuration remains optional.

- [ ] **Step 2: Verify every route and UI label against the code**

Do not describe a local fake run as evidence of a real model call.

- [ ] **Step 3: Link the guide from README and project status**

- [ ] **Step 4: Commit the task**

### Task 5: Full automated verification and handoff

**Files:**
- Modify: `docs/PROJECT_STATUS.md`

- [ ] **Step 1: Run frontend Vitest, ESLint, TypeScript typecheck, API drift check, and production build**
- [ ] **Step 2: Run the isolated PostgreSQL/Redis backend suite and Ruff**
- [ ] **Step 3: Confirm local Compose readiness and migration head**
- [ ] **Step 4: Record only fresh verification evidence in project status**
- [ ] **Step 5: Prepare the user’s GUI smoke checklist as the final manual review**

## Task graph

`1 -> 2 -> 3 -> 4 -> 5`

Tasks 1–3 deliver the guided user path. Task 4 records how to repeat it locally. Task 5 verifies the integrated result and leaves the final GUI review to the user.
