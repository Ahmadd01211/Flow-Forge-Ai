# Agent Tool Approval Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Pause agent runs before write-capable remote MCP calls, collect an independent owner/admin decision, and resume the exact approved continuation once.

**Architecture:** Add durable, encrypted agent approval state alongside `AgentRun`, with PostgreSQL as the authority for waiting, decision and call-claim transitions. Extend the existing execution API and trace, then add review controls to the trace UI; leave workflow approval behavior untouched.

**Tech Stack:** FastAPI, SQLAlchemy, Alembic, PostgreSQL, Celery, Next.js, TypeScript, pytest and Vitest.

**Spec:** `docs/superpowers/specs/2026-11-11-agent-tool-approval-design.md`

## Global Constraints

- Approval is required for write-capable remote MCP calls only.
- Decisions require a workspace owner/admin other than the requester.
- Continuation and arguments remain encrypted at rest; never place them in Redis messages or audit metadata.
- Approval expires after 24 hours and is invalidated by authorization, connection, schema, tool policy, or read/write classification changes.
- An external tool call with an ambiguous outcome is never replayed automatically.
- Existing workflow approval and local-only tool behavior remain unchanged.

## Review Focus

- Duplicate approval/queue deliveries must not execute a call twice (approval service/runtime tests).
- Requester or deployment authorization loss must fail closed (approval service tests).
- MCP permission/classification drift while waiting must invalidate the approval (MCP integration tests).
- Cancellation/expiry races must settle approval and release the run reservation once (service and reconciliation tests).
- Oversized/corrupt continuation data must fail safely without exposing plaintext (encryption tests).

## File Structure

- `backend/app/modules/executions/models.py`: waiting state and durable approval row.
- `backend/app/modules/executions/agent_approvals.py`: park, decide, claim, expire, and safe continuation operations.
- `backend/app/modules/executions/runtime.py`: park write-capable MCP calls and resume an approved call.
- `backend/app/modules/executions/worker.py`: waiting expiry and dispatch recovery.
- `backend/app/modules/executions/router.py`, `schemas.py`, `service.py`, `trace.py`: authorized decision route and pending-review summary.
- `backend/migrations/versions/0033_agent_tool_approvals.py`: schema migration.
- `backend/tests/test_agent_tool_approvals.py`, plus focused additions to agent run/MCP tests.
- `frontend/src/features/executions/run-trace.tsx`, trace model/types and API types: review panel and waiting state.
- `docs/superpowers/manual-tests/agent-tool-approval.md`: final GUI checklist and safe controlled-MCP test.

### Task 1: Durable State and Approval Service

**Files:**
- Modify: `backend/app/modules/executions/models.py`
- Create: `backend/app/modules/executions/agent_approvals.py`
- Create: `backend/migrations/versions/0033_agent_tool_approvals.py`
- Test: `backend/tests/test_agent_tool_approvals.py`
- Modify: `backend/tests/test_agent_runs.py`

**Interfaces:** `park(db, master, run, call, continuation, now)`, `decide(db, workspace_id, run_id, approval_id, actor_id, decision, master, now)`, `claim_approved(db, run, now)`, `reconcile(sessions, master, now)`. Keep authorization, encryption, lock order, audit and state transitions inside this module.

- [ ] Write failing tests for encrypted park, requester denial, owner/admin approval, duplicate decisions, reject, expiry, cancellation, and policy-context mismatch.
- [ ] Run those tests and confirm they fail for the expected missing model/service behavior.
- [ ] Add the `waiting` run state, partial active-run index update, `AgentToolApproval` table and migration.
- [ ] Implement row-lock order (`AgentRun`, then approval), scoped encryption, 24-hour expiry, independent review, idempotent same-decision handling and once-only approval claim.
- [ ] Run focused tests and relevant run/workflow pause regression tests.

### Task 2: Safe Agent Runtime Pause and Resume

**Files:**
- Modify: `backend/app/modules/executions/runtime.py`
- Modify: `backend/app/modules/executions/worker.py`
- Modify: `backend/app/modules/executions/harness.py`
- Test: `backend/tests/test_agent_tool_approvals.py`
- Test: `backend/tests/test_agent_mcp.py`

**Interfaces:** Runtime supplies a serializable provider transcript, exact pending MCP call, arguments, counters and tool context to `park`; resumed worker consumes an approved call before asking the provider for another step.

- [ ] Write failing runtime tests proving read-only calls execute immediately, write calls park before invocation, rejection never invokes, and approved continuation invokes once.
- [ ] Verify the tests fail for the expected runtime behavior.
- [ ] Add the non-failure `Parked` control path and durable continuation handling for write-capable MCP calls.
- [ ] Revalidate requester/deployment, provider credential generation, MCP generation/schema, Allow policy and unchanged write classification before network I/O.
- [ ] On an uncertain outcome after call claim, mark the run/trace uncertain and prevent automatic retry; persist cumulative token/cost data and preserve the original reservation.
- [ ] Run runtime, MCP, worker recovery, and cost-accounting tests.

### Task 3: API, Authorization, and Trace Data

**Files:**
- Modify: `backend/app/modules/executions/router.py`
- Modify: `backend/app/modules/executions/schemas.py`
- Modify: `backend/app/modules/executions/service.py`
- Modify: `backend/app/modules/executions/trace.py`
- Test: `backend/tests/test_agent_tool_approvals.py`
- Test: `backend/tests/test_agent_runs.py`

- [ ] Write failing API tests for authenticated pending summary, workspace isolation, requester denial, CSRF-protected approve/reject and deployment identity display.
- [ ] Verify expected failures.
- [ ] Add decision endpoint and `waiting` API state, returning only authorized trace summary and decrypting arguments only in the authenticated trace response.
- [ ] Run API, authorization, generated API drift and existing execution tests.

### Task 4: Review UI and Manual Test Path

**Files:**
- Modify: `frontend/src/features/executions/run-trace.tsx`
- Modify: `frontend/src/features/executions/trace-model.ts`
- Modify: `frontend/src/features/executions/run-console.tsx`
- Modify: `frontend/src/lib/api/types.ts`
- Add/modify: generated API types as required by repository workflow.
- Create: `docs/superpowers/manual-tests/agent-tool-approval.md`
- Test: focused run-trace and run-console Vitest files.

- [ ] Write failing UI tests for waiting-state presentation, owner/admin-only actions, hidden self-approval controls, and a clear cancelled/expired/uncertain status.
- [ ] Verify expected failures.
- [ ] Implement the review panel with service, tool, write warning, exact arguments, requester/deployment, expiry and approve/reject actions; stop test polling at `waiting` and link to trace.
- [ ] Add manual test steps with a no-paid-provider route and a controlled MCP write fixture.
- [ ] Run focused Vitest, full frontend checks and production build.

### Task 5: Full Verification and Handoff

**Files:**
- Modify any implementation/test files required by failures.
- Complete: `docs/superpowers/manual-tests/agent-tool-approval.md`

- [ ] Run full backend PostgreSQL/Redis test suite and Ruff.
- [ ] Run frontend Vitest, ESLint, TypeScript, API drift and production build.
- [ ] Exercise a controlled MCP test adapter end to end; record commands and outcomes.
- [ ] Inspect migration and git diff, confirm no secrets/plaintext continuation in audit or task payloads, and leave the final GUI walkthrough for the user.
