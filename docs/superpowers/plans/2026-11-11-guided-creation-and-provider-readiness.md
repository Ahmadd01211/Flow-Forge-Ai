# Guided Creation and Provider Readiness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task.

**Goal:** Let a non-developer start from a reviewed recipe, configure only what is needed, understand skill/provider readiness, and reach a safe test or publish action.

**Architecture:** Keep template instantiation as the single seam that creates workspace-owned agent/workflow drafts. Extend static recipe metadata to describe setup and starter skills, and make skill-copy plus draft attachment atomic. The existing skill publication, provider, readiness, preview and run systems remain authoritative; the frontend explains and routes through them rather than creating alternate execution behavior.

**Tech Stack:** FastAPI, SQLAlchemy, Pydantic, pytest; Next.js, React, TypeScript, Vitest, existing CSS tokens and Lucide.

**Spec:** `docs/superpowers/specs/2026-11-11-noncoder-creation-experience-design.md`

## Global Constraints

- Existing published agent/skill/workflow versions remain immutable; template use creates a new workspace-owned draft.
- Provider keys stay encrypted and are never returned or copied into recipes. A user-provided key is only used to verify a connection on the server.
- Permission, cost and side-effect policies remain server-authoritative. A UI recommendation cannot grant a tool or bypass publication checks.
- Preserve the current split between local draft preview, node tests subject to confirmation/receipt checks, and durable published workflow runs.
- Skills copied from recipes are drafts; the guided path must explicitly include review and publication before test, then surface re-publication when edits make the attached version stale.
- Call recipe-created resources workspace drafts, not private drafts, until the product implements access-controlled private visibility.

## Review Focus

1. A recipe containing a missing/archived starter skill returns no partial agent or skill records; test rollback and safe retry.
2. Re-instantiating a recipe creates independent skill copies with distinct workspace-owned IDs; test two instances.
3. A skill edit after publishing keeps the old immutable version and tells the user the draft changed; test readiness states.
4. Provider verification/catalog failures keep entered key state safe and expose actionable errors; test invalid key, network/catalog failure and success paths using mocks.
5. Workflow recipe guidance distinguishes local preview from publish-required durable runs; test recipe category/requirements mapping and frontend copy.

---

### Task 1: Recipe skill metadata and atomic skill-copy instantiation

**Files:**
- Modify: `backend/app/modules/templates/catalog.py`
- Modify: `backend/app/modules/templates/router.py`
- Modify: `backend/app/modules/skills/service.py` only if a focused copy helper is needed
- Test: `backend/tests/test_templates.py`

**Interfaces:**
- Input remains `POST /workspaces/{workspace_id}/templates/{template_key}/instantiate`.
- Extend reviewed built-in agent recipe definitions with optional `starter_skills: list[str]` and user-facing `setup_steps`, `sample_input`, and `expected_result` metadata. Use these exact mappings: `support-triage` → `plain-language`; `faq-answer` → `plain-language`, `summarise-sources`; new `customer-reply-draft` → `brand-voice`, `polite-refusal`; new `meeting-action-items` → `extract-tables`.
- `customer-reply-draft` accepts `customer_message` and `brand_guidelines`; returns `draft_reply` and boolean `needs_human`; sample is a neutral shipping-status question with empty brand guidelines.
- `meeting-action-items` accepts `notes`; returns `summary` and `action_items` array with `task`, `owner`, and `due_date` strings; sample is a short meeting note containing two assignments and one missing due date.
- Response adds `skill_ids: list[uuid.UUID]` for created copies; preserve current `kind`, `id`, and `template_key` fields.
- Skill copies are editable, unpublished workspace skills, created in the same database transaction as the agent and attached using `AgentConfig.skills` grants.

- [ ] **Step 1: Write backend tests first** for all four skill mappings and valid agent schemas, new recipe sample/expected-result metadata, duplicate instantiation, missing starter rollback, and workflow instantiation preserving existing response fields.
- [ ] **Step 2: Run those tests and confirm the skill-copy/attachment and rollback assertions fail for the intended missing behavior.**
- [ ] **Step 3: Add the two reviewed agent recipes and skill metadata to the static catalog, then implement one transaction-scoped copy path.** Resolve starter keys from `STARTERS`; copy only name, description, instructions, examples and `starter_key`; never copy tool grants or credentials. Attach the resulting skill ID and display name to the agent config before saving. Expected-result copy explains that output is a draft for human review.
- [ ] **Step 4: Re-run focused tests; verify copies are drafts, distinct per instantiation, attached, and rollback cleanly.**
- [ ] **Step 5: Run relevant template/skill backend tests and commit.**

### Task 2: Guided recipe discovery and honest setup/test states

**Files:**
- Modify: `frontend/src/features/workspace/task-start-model.ts` and its tests
- Modify: `frontend/src/features/workspace/task-start.tsx`
- Modify: `frontend/src/features/templates/template-gallery.tsx`
- Modify: `frontend/src/app/w/[workspaceId]/templates/page.tsx` only if response typing requires it
- Test: adjacent Vitest suites for task start and template gallery

**Interfaces:**
- Preserve existing `/w/{workspaceId}/start` and `/templates` routes.
- Template detail supports optional `setup_steps`, `sample_input`, `expected_result`, and `starter_skills` display metadata.
- Instantiation response `skill_ids` routes the user to the created agent with explicit “review and publish skills” guidance.

- [ ] **Step 1: Add model/UI tests** for recipe search/filter, category selection, previewing result/setup/skills, workspace-draft visibility copy, and the different workflow preview versus published-run instructions.
- [ ] **Step 2: Run focused tests and observe failures for the missing recipe journey.**
- [ ] **Step 3: Build a task-first gallery path that previews before creating.** Use clear task-language cards, required-setup labels, expected result, sample data, permissions/cost signals, and one primary create action. Keep advanced template import/export available.
- [ ] **Step 4: After instantiation, show the created workspace draft status and route to the existing editor.** For agent recipes with skills, identify each attached skill and route to its editor/library; explicitly state that an attached skill must be reviewed and published before agent test/publish. Explain that edits require publishing a new immutable skill version. For workflow recipes, use local preview where available and explain publication before durable full runs when required.
- [ ] **Step 5: Run focused frontend tests, typecheck and lint; commit.**

### Task 3: Provider-flow diagnosis and actionable recovery

**Files:**
- Inspect and modify only if tests reproduce a defect: `frontend/src/features/workspace/provider-connection.tsx`, provider-specific frontend helpers, and matching integration backend adapter/router.
- Test: adjacent provider-connection Vitest suite; existing backend integration/provider test modules.

**Interfaces:**
- Preserve existing provider connection endpoints and provider identifiers.
- Keep provider secrets server-side; user-facing error copy contains no key material or raw credential-bearing request data.
- Provider setup flow distinguishes key verification, model discovery, and runnable model selection.

- [ ] **Step 1: Write component/model tests** for successful key verification and model selection/save, rejected credentials without key echo, provider switching clears the unsaved key/error, model catalog refresh failure preserves the prior backend catalog/default, and empty model states distinguish “no runnable models” from “no search matches.”
- [ ] **Step 2: Run the tests and reproduce any failure.** The existing UI computes `models` from verified models then filters out non-runnable entries by default; specifically check the reproducible state where `verified_models` is nonempty, all capabilities are setup-only, and the search is empty. Record exact rendered copy and layer.
- [ ] **Step 3: Trace any failing value through UI → API client → integration router/service → provider adapter → returned state.** Change one root cause only after the failure is localized. When existing behavior is correct, retain it and add coverage; improve recovery copy only for an ambiguous state the test demonstrates.
- [ ] **Step 4: Re-run focused and existing provider integration tests.** Never call a live provider without user-provided credentials.
- [ ] **Step 5: Run frontend typecheck/lint and relevant backend tests; commit.**

### Task 4: Manual walkthrough, status docs, and review

**Files:**
- Modify: `docs/PROJECT_STATUS.md`, `docs/DEVELOPMENT_PHASES.md`, and add a concise manual GUI checklist under `docs/`.

- [ ] **Step 1: Add exact manual steps** for local workflow recipe preview, agent recipe plus skill publish/test, provider setup with the user's own key, and publish-required workflow run.
- [ ] **Step 2: Correct template/skill counts and feature status from source inventory.**
- [ ] **Step 3: Run backend and frontend verification commands from package scripts.**
- [ ] **Step 4: Review user-facing wording and commit.**

## Delivery Note

The requested Design Report DOCX must use its retained reference and be rendered for visual verification. The available document capability currently lacks a Word session and LibreOffice renderer, so that artifact remains ungenerated until a supported renderer is available; this does not block implementation or the Markdown design/spec/plan.
