# First implementation: a real workspace and editable drafts

## What now exists

Next.js renders the landing page, account forms and private workspace. FastAPI stores accounts, server sessions, workspace ownership, agent drafts and workflow graphs in PostgreSQL. Redis supplies shared authentication rate limits. Celery is installed and locked but no execution workers or provider calls are enabled yet.

The workflow builder uses XYFlow for nodes/connections, local state for unsaved changes and a FastAPI endpoint for persisted structural validation. Structural validity does not imply publication/execution readiness; the interface says that explicitly.

## Follow a registration

1. React Hook Form/Zod checks immediate form feedback.
2. Browser obtains a CSRF token bound to an HttpOnly pre-auth cookie.
3. FastAPI checks Origin and CSRF, then rate limits attempts through Redis.
4. Password becomes an Argon2id hash. User, owned workspace, membership and session commit together in PostgreSQL.
5. Browser receives a new opaque HttpOnly session cookie. Only its hash is stored in the database.
6. Next.js server-rendered workspace reads forward that session to FastAPI; the backend checks membership again.

Why: a hidden sidebar item cannot enforce security. The API must reject unauthorized reads and writes regardless of what the browser sends.

## Follow a save

Agent/workflow form keeps local unsaved state. Save includes expected_revision. Backend locks the draft, checks ownership and revision, writes the new document and increments revision. If another tab already saved, the stale request receives 409 instead of replacing newer data. The UI keeps your edits and reports the conflict.

Why: this is the smallest practical defense against lost updates without introducing collaborative editing infrastructure.

## Follow graph validation

API validates the stored graph revision, not an untrusted browser claim that it passed. A pure function finds cycles, missing endpoints, duplicate connections, disconnected nodes and invalid ports. It reports unavailable agent/tool dependencies. Position and display-label edits do not change the semantic execution hash.

Why: visual layout is presentation. Dependency direction and configuration determine behavior. Full schema/mapping/branch validation must be added before publication is allowed.

## Deliberate boundaries

No live provider credentials, immutable agent/workflow publication, run submission, Celery runtime, execution history or usage ledger yet. Settings currently shows identity/role, not member administration. Pending capabilities are clearly labeled and do not show fake successful results. No screenshot automation was performed.

## What comes next

Strengthen and freeze the definition contracts, then implement immutable snapshots and one provider adapter. Follow with durable submission/outbox, budgets/checkpoints, bounded execution and monitoring. Keep the existing canvas connected as those capabilities arrive. Queue wait timeout and execution timeout will be separate bounded policies, as agreed in the recommendations.
