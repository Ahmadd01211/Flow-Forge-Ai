# Durable workflow checkpoints and debugging

## What changed

Executions now has separate Agent runs and Workflow runs views. Workflow history shows status, recorded usage, selected branches, skipped steps and attempts. Select a step to inspect its encrypted-at-rest input/output evidence. The builder and automation history link directly to this debugger. History lists return summaries; payloads are decrypted only for a selected run or step.

Each workflow step has a bounded encrypted checkpoint in PostgreSQL, unique to its run/node and execution sequence. The encryption context binds the workspace and checkpoint identity. Running, completed, skipped and failed states are recorded independently of the final workflow result. A later failure therefore preserves earlier step evidence.

## Recovery boundary

The worker owns a claim token on the run. Every checkpoint write locks that run and verifies the current token. Recovery invalidates the previous token before another worker can proceed; a stale worker cannot replace newer evidence or start another external call.

Checkpoint writes update a progress heartbeat. If safe work loses its worker, maintenance can requeue it after ten seconds without progress, within the original run deadline. Recovery traverses the same immutable graph and reuses completed/skipped checkpoints. Only unfinished pure local work is repeated. Legacy pre-call runs retain the earlier conservative recovery behavior.

Before an agent/MCP request, the run records an external-inflight marker. A completed external step clears it only after the result checkpoint commits. If the worker disappears during the request or before its result is safely checkpointed, the operation is not automatically replayed. The original deadline expires it, unfinished step records become failed, and known/uncertain costs remain visible. This explicitly handles the response-lost-before-checkpoint window; exactly-once external effects cannot be promised without cooperation from the remote API.

## Policies and explicit replay

Step timeouts accept whole seconds from 1 to 300; effective provider/MCP request limits also respect the shared workflow deadline and platform caps. The workflow deadline includes queue time and takes the smaller configured/platform allowance. Local previews remain bounded to five seconds; durable local-only runs to fifteen seconds; workflows with external steps to thirty seconds.

Local retry policies permit one to three attempts. Only classified temporary local availability errors and step timeouts retry, with a short bounded delay. Input/schema/mapping failures stop immediately. Agent and MCP nodes require one request attempt. Recovery attempts after a process loss are distinguishable in the persisted attempt count and do not imply an additional provider request when a completed checkpoint exists.

Replay creates a new run using the original published version and encrypted input. It requires a terminal source run, a fresh replay idempotency key, current credentials/permissions and normal workspace admission limits. External replays require explicit confirmation because they can repeat requests and charges. The original run is preserved, and the audit log links the new run to its source. Duplicate replay requests with the same key return the same new run. The frontend retains that key while retrying an uncertain submission response.

## Design decisions

Keep per-step records rather than repeatedly rewriting one cumulative encrypted run document: each input/output is bounded, targeted inspection is cheap, and completed evidence can be reused after a crash. Keep PostgreSQL as the checkpoint authority so Redis remains disposable delivery transport. Reconsider a dedicated execution engine only if measured workload, long-lived waits, concurrency or orchestration semantics exceed this bounded DAG runner.

Use conservative replay rules rather than retrying every network error. A timeout does not prove that the remote operation failed. Reconsider automatic external retries only for explicitly idempotent operations with a reliable remote request identity and tested deduplication behavior.

Register all ORM models at each independent process composition root. A real worker startup test found that API-only imports had hidden missing model registrations from unit/integration tests. API, migrations and workers now share `app/models.py`; a fresh Celery subprocess completes a fan-out/merge run through real Redis/PostgreSQL.

## Evidence and limits

Integration tests simulate process loss before a second agent request and prove the first agent is not called again; reject stale-claim checkpoint writes; preserve encrypted evidence after failures; withhold recovery during an ambiguous external call; expire it safely; and enforce replay confirmation, deduplication, tenant isolation and active-run restrictions. Policy tests distinguish temporary local recovery from permanent errors and verify external timeout forwarding. Readiness now checks both database/migration state and Redis.

Migration `0020` is additive and preserves conservative markers on legacy in-progress external runs. Older completed runs retain their existing final trace; they have no new per-step input evidence. Scoped subworkflows and bounded For each loops are now delivered in [phase 6 composition](19-WORKFLOW-LOOPS-AND-SUBWORKFLOWS.md), using migration `0022` for up to 120 expanded checkpoints. Durable human waits, advanced attempt history and operator observability remain later slices.
