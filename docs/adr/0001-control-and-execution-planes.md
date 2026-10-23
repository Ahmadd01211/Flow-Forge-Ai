# ADR 0001 — modular control plane and durable worker execution

Initial decision sketch; see the [final decision register](../technical-architecture/07-DECISIONS.md) for approval, alternatives and reconsideration triggers.

Status: proposed, pending package approval.

Decision: Next.js provides presentation; FastAPI owns authorization, definitions, validation and run submission. PostgreSQL persists execution truth. Celery/Redis deliver bounded work to separate agent/workflow worker pools. Transactional outbox closes commit/dispatch gaps; leases and fencing handle duplicate delivery and abandoned work.

Reason: durable inspection and bounded execution matter more than early service decomposition. A modular monolith keeps transactions and ownership rules understandable while workers scale separately.

Tradeoffs: outbox relay/reconciler add operational responsibilities; external exactly-once effects remain impossible without destination support. Avoid microservices and Temporal initially. Reconsider orchestration technology when long-lived timers/approvals become core requirements.
