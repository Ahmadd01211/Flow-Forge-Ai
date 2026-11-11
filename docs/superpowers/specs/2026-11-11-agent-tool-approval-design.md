# Durable Approval for Agent Tool Calls

## Intent

Let workspace users safely use an agent that has write-capable remote tools without letting the model perform a consequential action before a person reviews that exact call. When a write-capable tool is requested, the run must pause, show the reviewer the tool and arguments, and resume the same run only after an authorized approval.

The project roadmap names this as the next agent-harness slice. Conversation memory is already implemented, so the older delivery-order text that lists memory as the next feature is stale.

## Goals

- Pause before every write-capable remote tool invocation made by the agent loop.
- Persist enough encrypted execution state to resume the exact model continuation and approved tool call after a worker exits or restarts.
- Require an independent workspace owner/admin decision by default; the run requester cannot approve their own call.
- Show the reviewer the service/server, tool, effective permission, exact bounded arguments, requester, and expiry.
- Recheck run authorization, agent version, current connection generation, and current tool policy before executing the approved call.
- Guarantee the same approved call is not automatically sent twice after an ambiguous external outcome.
- Keep model token/cost accounting, run reservations, active execution limits, and audit history accurate across a pause.
- Provide a clear waiting state and review/decision UI in the existing execution trace.

## Non-goals

- No approval pause for read-only remote calls, reviewed local tools, skill loading, or current local-only workflow calls.
- No new approval rules for workflow nodes; their existing Human approval step remains unchanged.
- No requester self-approval setting, approver groups, quorum, delegation, notifications, or multi-stage approvals.
- No remote callback or email approval links.
- No automatic replay after a write call has an unknown outcome, and no “retry action” button in this slice.
- No change to MCP Allow/Block policy, agent grants, role definitions, provider adapters, or tool contracts.
- No public hosting, OAuth, billing, or general workflow orchestration work.

## Approaches considered

1. **Persist and resume the exact agent continuation.** Add a waiting state to agent runs and an agent-specific durable tool-approval/checkpoint record. Save the provider transcript and exact pending tool call encrypted, exit the worker, and queue the same run after approval. This preserves the agent’s tool-loop semantics and reuses the existing agent run queue, reservation, trace, audit, authorization, and maintenance patterns. **Selected.**
2. **Generalize workflow pause records to cover both run types.** This could eventually share more code, but `WorkflowPause` is tied to workflow run/checkpoint foreign keys, node identity, and workflow input hashes. Replacing that model now would widen the migration and recovery risk across a stable workflow path.
3. **Require users to move consequential actions into workflows.** Workflow Human approval already provides a durable approval path, but this does not resume the agent’s own model/tool conversation and leaves the requested agent-harness gap unresolved.

## User-visible behavior

When an agent requests a write-capable MCP tool, FlowForge validates the call arguments and saves a pending approval before invoking the remote service. The run changes to **Waiting for approval** and the worker exits. The run trace shows the request with service, tool, arguments, requesting user, and expiry. A different workspace owner/admin may approve or reject it.

Approval queues the existing run. A worker claims the saved continuation, verifies the requester and published version are still authorized, verifies the connection generation and tool remain allowed and write-capable, then makes the single approved call. Its output is appended to the saved provider transcript and the model loop continues. Rejection or expiry ends the run with a clear error. Revoked permissions fail closed. Read-only remote calls continue without a human pause.

The approval identifies one exact call and is bound to its run, immutable agent version, tool key, canonical arguments hash, effective read/write classification, and encrypted continuation. Editing a draft cannot alter a pending call. Changing arguments requires a new model request and a new approval.

## System design

### Existing seams

- `backend/app/modules/executions/runtime.py` owns the provider tool loop and currently invokes a validated function call immediately.
- `AgentRun` in `executions/models.py` currently has queued/running/terminal states; `executions/worker.py` reconciles and dispatches those runs.
- `RunEvent` and `executions/trace.py` persist and display encrypted tool arguments/results and model usage.
- `backend/app/modules/workflows/pauses.py` is a proven reference for lock ordering, independent review, deadlines, worker release, authorization checks, auditing, and conservative recovery. Its rows and checkpoints remain workflow-specific.
- `frontend/src/features/executions/run-trace.tsx` is the existing user surface for agent run status, timeline, input/output, and tool evidence.

### Agent approval module

Add a focused module under executions (proposed `agent_approvals.py`) that owns creation, pending reads, decision, expiry, resume preparation, and once-only execution claiming for an agent tool approval. Its public interface should stay small: park the pending tool call, decide approve/reject, and reconcile expired approvals. The provider loop should not implement reviewer-role, row-lock, audit, encryption, or recovery policy itself.

The module stores a separate `AgentToolApproval` record linked to `(workspace_id, run_id)`. The record contains the opaque tool key, pending/settled state, requester and reviewer references, created/expiry/settled timestamps, canonical argument hash, and encrypted continuation nonce/ciphertext. The encrypted continuation contains the provider transcript, exact provider function-call item/call ID, validated arguments, cumulative token/call counters, and any adapter state needed to continue the same loop. No provider transcript or argument JSON goes into audit metadata or Celery messages.

Use the existing credential encryption helper with workspace/run/approval-scoped associated data. Never store credentials, provider keys, or decrypted continuation in Redis. Bound the serialized continuation to the existing run context limit before parking; reject or fail safely if it exceeds the bound.

### Run states and capacity

Add `waiting` to the `AgentRun` database constraint and API literal. A waiting run has no active worker claim and is not eligible for normal agent dispatch. It remains within the existing execution deadline as active time: when resumed, shift `deadline_at` by the parked duration, subject to a maximum approval wait of 24 hours. It retains the existing workspace active-run slot and model-budget reservation while waiting, matching current workflow approval behavior. Cancellation, expiry, authorization revocation, or workspace policy revocation settles the approval and run and releases the reservation through the existing completion path.

Do not reuse or reset the original run budget. Persist token totals and model costs reached before the pause so run history and cost reservation reconciliation remain correct while waiting. Resume only the remaining token/cost allowance from the original admission.

### Tool-call flow and once-only execution

1. Receive the provider function call, map it to the published version's pinned grant, parse and validate its arguments, and recheck the effective current Allow/Block policy.
2. If the resolved tool is read-only, follow the current immediate invocation path.
3. If it is write-capable, encrypt the complete continuation, create a pending approval and a pending trace event, transition the run to waiting, clear its claim, and commit those changes atomically. Raise a non-failure control exception so the worker returns normally rather than retrying the call.
4. On approval, lock the run first and the approval second; enforce owner/admin role and independent review; bind the decision to the canonical hash and run/version/tool identity; settle and queue the same run in one transaction. An identical retry by the same reviewer returns the settled result; conflicting or stale decisions return a conflict.
5. A resumed worker atomically claims the approved call before network I/O. Recheck run/deployment requester authority, provider credential generation, MCP connection generation, schema, and current tool allow/write policy immediately before the call. The effective read/write classification must still match the classification shown at approval time; any change invalidates the approval and fails closed, even if the tool now appears read-only.
6. Record the call result and consume the saved continuation once. If a worker dies or a network outcome is unknown after the call is claimed, mark the tool result/run uncertain and never automatically replay it. A later explicit product decision may add a human reconciliation path; it is outside this slice.

```mermaid
sequenceDiagram
    participant M as Model provider
    participant W as Agent worker
    participant D as PostgreSQL
    participant R as Reviewer
    participant T as Remote tool
    M->>W: Write-capable tool call
    W->>W: Validate pinned tool and arguments
    W->>D: Encrypt continuation + create pending approval + set run waiting
    W-->>W: Exit worker; release claim
    R->>D: Approve or reject exact call
    alt Approved and still authorized
        D->>D: Settle decision and queue same run
        D-->>W: Dispatch run ID
        W->>D: Claim approved call once
        W->>T: Execute exact approved arguments
        T-->>W: Result
        W->>D: Save result and resume provider transcript
        W->>M: Continue agent tool loop
    else Rejected, expired, or revoked
        D->>D: Fail run; do not invoke tool
    end
```

### Authorization and audit

- Only workspace owners/admins may decide.
- The requester cannot approve their own call. Deployment-originated calls retain the deployment creator/requester identity used by existing run authorization. The review panel shows the deployment name and its creator as requester. Existing authorization requires that creator to remain an owner/admin; if that authority is revoked or the deployment is revoked, the pending run fails closed.
- Recheck the requester/deployment permission after admission, at resume, and immediately before the remote call.
- Recheck the current MCP effective policy and effective read/write classification before execution; an approval does not override a later Block, connection revocation, or policy/metadata change. Any change from the classification that was reviewed invalidates the pending approval and requires a new run/review.
- CSRF protection applies to decisions. No hosted bearer key, public URL, or callback may approve an action.
- Record `agent_tool_approval.created`, `approved`, `rejected`, `expired`, `cancelled`, and `execution_uncertain` audit events with IDs and tool identity only. Do not include arguments or transcript in audit JSON.
- The execution trace shows pending/approved/rejected/expired/failed tool status and decrypts arguments only through the existing authenticated trace view.

### API and UI

- Extend `RunRead.state` and run-list types with `waiting`.
- Include the pending approval summary in the authenticated run detail/trace response: approval ID, tool identity/label, safe description, bounded arguments, requester, expiry, decision status, and whether the current viewer may decide. Role checks remain server-side.
- Add a CSRF-protected decision endpoint scoped under the workspace/run/approval; request body is exactly `approve` or `reject`.
- Add a review panel to the existing run trace for waiting calls. It displays the exact arguments and write warning, and shows Approve/Reject only for a current owner/admin who is not the requester. After decision, show the settled result and trace status.
- Update the agent test panel so polling stops on `waiting` and links to the run trace rather than displaying an indefinite “still running” message.
- Add an Executions list status label/filter for waiting runs and link each to its trace. No notification system is included.

## Failure and recovery rules

- Pending approval older than 24 hours expires, fails the run, settles the reservation, and is never executed.
- Run cancellation while waiting atomically cancels the approval and run.
- Role removal, requester/deployment authorization revocation, version invalidation, credential rotation, tool policy change, or effective read/write classification change prevents execution when approval is decided or immediately before the tool call.
- Duplicate decision submissions do not dispatch duplicate work. Duplicate queue delivery is ignored unless the run and approval are in the correct queued/approved state.
- A failure before the external call begins may be retried only when the once-only claim proves no call was started. Once the external call may have begun, recovery is conservative and never resends it.
- A rejected call records `AGENT_TOOL_APPROVAL_REJECTED`; an expired call records `AGENT_TOOL_APPROVAL_EXPIRED`; revoked permission records the existing tool revocation error where compatible.
- Output/token totals include provider calls that happened before the pause. Rejection/expiry do not erase already-incurred provider charges.

## Verification and acceptance

- Database tests cover waiting-state constraints/indexes, encrypted continuation round-trip and bounds, pending→approved/rejected/expired/cancelled transitions, atomic queueing, independent review, workspace/role isolation, idempotent decisions, deadline shifting, reservation retention/release, requester/deployment revocation, credential rotation, tool Block/revocation, and cancellation races.
- Runtime tests prove read-only tools still execute without pausing; write-capable calls park before any remote invocation; approved calls execute once and continue the same provider transcript; rejection/expiry never invoke the remote tool; ambiguous outcomes are not replayed; and prior model cost/token usage is preserved.
- Recovery tests kill or duplicate workers before approval, after approval but before call, during a possible external call, and after the result is persisted. Only the no-call-start case may be retried.
- API/UI tests verify pending-call summaries, reviewer visibility, requester denial, tool arguments and read/write labels, waiting-run navigation, and waiting-aware test-panel polling.
- Run the full PostgreSQL/Redis suite, Ruff, frontend Vitest, ESLint, TypeScript, API drift, and production build. Exercise a local run against a controlled MCP test adapter; no real write-capable service or paid provider call is required for acceptance.
- Leave final manual GUI confirmation to the user with a no-provider setup path and an explicit safe write-tool test procedure.

## Constraints and builder choices

- Existing PostgreSQL, Redis/Celery, FastAPI and Next.js architecture remains in use; no new orchestration service or dependency is required.
- Published agent versions stay immutable. Approval is for one runtime call, not a mutation to the version's tool grants.
- Deployment runs use the deployment creator as `AgentRun.requested_by`; the existing worker authorization already requires that creator to remain an owner/admin. The approval UI should identify both the deployment and its creator, while preserving the same independent-review rule used for direct runs.
- MCP effective read/write classification is part of the approval context. If it changes while waiting, do not reinterpret the old approval or silently execute under the new classification; settle the approval as stale and fail the run with a clear context-changed error.
- Continue to use the existing run budget, usage admission, authorization, credential encryption, MCP registry and audit modules as the source of truth.
- The builder chooses the exact model/schema names and UI component placement, provided lock order, encrypted data, waiting semantics, and once-only side-effect rules above are preserved.
- This phase does not include live acceptance against real write-capable MCP accounts; that remains a separate user-configured integration check.
