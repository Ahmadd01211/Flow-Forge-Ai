# FlowForge AI — final technical architecture proposal

Prepared 18 October 2026. Status: **baseline approved; implementation started after the user's explicit instruction**. The documents below preserve the pre-implementation architecture proposal; [PROJECT_STATUS.md](../PROJECT_STATUS.md) records what is actually implemented.

The initial product direction is approved. This proposal resolves technical details before scaffolding. Source of truth: supplied Greenfield Master Project Instructions, the approved [Product Design Specification](../DESIGN.md), and the user's latest architecture-only request. Only this FlowForge AI folder and supplied attachments were inspected; ResearchPilot is outside scope.

## Read in this order

1. [System design](01-SYSTEM.md): C4 diagrams, backend modules, frontend routes and boundaries.
2. [Data model](02-DATA.md): ownership, ER diagram, constraints, indexes and transactions.
3. [Contracts and schemas](03-CONTRACTS.md): REST, agent versions and workflow graph JSON Schema.
4. [Execution and recovery](04-EXECUTION.md): state machines, branching, budgets, delivery and failure recovery.
5. [Security](05-SECURITY.md): identity, roles, tools, secrets and SSRF.
6. [Development and operations](06-OPERATIONS.md): Compose topology, tests, CI and observability.
7. [Decision register](07-DECISIONS.md): why each major choice fits, alternatives and reconsideration triggers.
8. [Implementation and learning guide](08-IMPLEMENTATION-AND-LEARNING.md): independently testable slices and explanations at each step.

## Approval scope

Approve a modular monolith control plane with independently scalable, bounded execution workers. Next.js App Router/TypeScript/Tailwind handles presentation; FastAPI owns business rules and authorization; PostgreSQL stores durable definitions and execution state; Redis/Celery deliver tasks. No microservices, Temporal, arbitrary user code, scheduled/webhook entry points or decorative integrations in MVP.

The flagship remains the three-panel visual workflow builder. Its published graph is an execution contract, not just a diagram. Every run pins immutable versions. No UI completion state appears before durable backend completion.

Proposal-specific defaults are tunable policy values, not provider guarantees. Framework/package patch versions will be selected, compatibility-tested and locked during the approved foundation slice; this document does not claim a deployment exists.

## Coverage of the requested package

| Requirement | Primary document |
|---|---|
| 1. C4 context/container/components | 01 |
| 2. Backend structure/dependencies | 01 |
| 3. Next.js routing/server-client boundaries | 01 |
| 4. PostgreSQL ER/ownership/constraints/indexes | 02 |
| 5. Versioned REST | 03 |
| 6. Agent configuration/immutable versions | 03 |
| 7. Agent states/cancel/timeouts/retries/budgets | 04 |
| 8. Typed graph schema/branches/validation/versions | 03, 04 |
| 9. Durable Celery/Redis/PostgreSQL execution/recovery | 04 |
| 10. Tools/credentials/SSRF | 05 |
| 11. Authentication/workspace authorization | 05 |
| 12. Compose topology | 06 |
| 13. Tests/CI/logging/observability | 06 |
| 14. Small vertical slices | 08 |
| Reasons/alternatives/reconsideration triggers | 07 |
| Teaching from decisions through code | 08 |

## Changes from the initial sketch

- One JSON graph snapshot is authoritative; do not maintain duplicate editable graph JSON and node/edge tables.
- Agent drafts may be tested through immutable test snapshots without publishing them for workflow use.
- Branch routing is recorded per edge; merges wait for all incoming edges to resolve. Skipping is not propagated blindly to all descendants.
- A lost provider response or external effect is an uncertain outcome, not permission for an automatic retry.
- Outbox delivery is supplemented by queued-work reconciliation, so broker data loss does not strand work marked delivered.
- Start with polling and one maintenance process for relay/reconciliation; do not add SSE, an integration worker or an orchestration service prematurely.
- Cookie authentication uses a single browser origin, with FastAPI authoritative for both browser and server-rendered reads.

## Source notes

Framework/security behavior was checked against primary documentation. The architecture and policy choices are project proposals. References sit beside the relevant behavior; follow their links for exact framework details. This package supersedes technical sketches in the parent docs folder wherever they differ. DESIGN.md remains the visual/product source of truth; the immutable test snapshot clarifies its test-before-publish journey.
