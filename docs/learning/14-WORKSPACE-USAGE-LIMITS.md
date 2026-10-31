# Workspace usage and admission limits

## Why a shared limit

A per-agent run budget does not stop a schedule or external client from starting many individually cheap runs. The Usage page now reads the durable agent/workflow ledgers and shows measured model cost, active reservations, possible uncertain charges, accepted runs and tokens. All run-entry paths use the same admission control: the playground, agent node tests, workflow runs, deployments, webhooks and schedules.

Each workspace starts with a $10 daily model budget, 1,000 accepted runs per UTC day, and four active runs shared across agents/workflows. The existing maximum of two active runs per type also applies. An owner/admin can set a daily budget from $0 to $10,000, accepted-run limit from 1 to 10,000, and active limit from 1 to 4. Settings changes have revision checks and metadata-only audit records. Members can read usage; only admins/owners can change limits. Changing limits does not cancel accepted runs.

These are application admission limits for customer-provided provider keys, not subscriptions, credits or a guarantee about the provider invoice. Costs use FlowForge's reviewed token price estimates. MCP service fees are outside these figures.

## Reservation lifecycle

1. Lock the workspace row. Every run submission uses this same PostgreSQL lock.
2. Return an existing idempotent run before consuming capacity again.
3. Check version, input, provider credentials, tool permissions and the run budget.
4. Sum recorded cost, uncertain charges and active reservations; check daily run count and shared capacity.
5. Insert the encrypted durable run and its reservation within the same transaction.
6. Release the lock on commit. Concurrent submissions then see the accepted reservation.

Standalone runs reserve a bounded input/output estimate, rounded upward to the ledger's eight-decimal precision. Tool loops reserve their whole configured run budget. Workflows with an agent reserve the workflow budget; pure local/read-only MCP workflows reserve zero model tokens. This conservative workflow reservation may exceed the eventual agent cost but is released after the run settles.

On completion, recorded usage replaces the reservation. Cancelling a queued run releases its model reservation while retaining its accepted-run count. A failure before any model request releases it; an ambiguous provider outcome preserves a possible-charge estimate. Invalid negative, boolean or string token counts cannot reduce the ledger.

## UTC windows

Daily counts and measured/uncertain totals are attributed to the UTC day the run was accepted. Active runs from an earlier day retain a reservation in the current admission calculation. Therefore midnight cannot briefly free every active reservation. The page displays the exact reset time in the viewer's local time and explains its UTC boundary.

A zero budget blocks paid model admissions while allowing zero-model-cost workflows within count/capacity limits. Lowering a budget beneath recorded commitments blocks further paid admissions. Exceeding a run count waits until the next UTC day. A scheduled occurrence that hits daily-count capacity keeps its due slot and retries after midnight. Budget pressure retries after sixty seconds; active-capacity pressure retries after ten seconds. The scheduler never turns an admission failure into a paid request.

## Design decisions

Use aggregates over existing durable run records rather than introducing a second money ledger: the current volumes are bounded and this avoids drift between execution truth and accounting truth. Existing workspace/date history indexes plus new partial indexes for active workspace runs support these queries. Reconsider pre-aggregated ledger entries and settlement transactions after measured query costs or retention volumes justify them.

Use PostgreSQL row locks rather than Redis counters for reservation authority: acceptance, reservation and idempotency must commit together even if Redis restarts. Redis remains suitable for request throttling. Reconsider more granular locking only when admission throughput for a single workspace becomes a measured bottleneck.

Use UTC daily limits before billing integration: users can inspect and control their own automation without a payment-service dependency. Monthly plans, platform-owned quotas, paid entitlements, subscription webhooks and trusted reconciliation of uncertain charges remain later work. Public hosting should also impose operator-owned ceilings that a tenant admin cannot raise.

## Verification

PostgreSQL integration tests cover reserve-to-measured settlement, cancellation release, duplicate submissions, paid-budget denial, zero-cost workflow admission, uncertain charges, cross-type concurrency, daily accepted counts, concurrent transactions, UTC carry-in, revision conflicts, role/tenant/CSRF checks, numeric boundaries and paid workflow reservations. Migration `0019` adds default workspace policies, backfills reservations for existing active agent workflows and adds active-workspace indexes.
