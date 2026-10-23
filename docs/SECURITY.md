# Security threat model

Initial sketch, superseded by the [final security design](technical-architecture/05-SECURITY.md).

Assets: sessions, workspace definitions, provider credentials, sensitive inputs/outputs, execution authority and spend. Trust boundaries: browser→API, API→database/broker, worker→provider/tool destination, tenant→tenant. Everything below is a requirement, not an implemented guarantee.

| Threat | Required mitigation | Verification |
|---|---|---|
| Cross-tenant resource access | Workspace authorization on every read/write; tenant-scoped FK relationships; worker verifies ownership | Two-workspace API and worker tests |
| Session theft / CSRF | Random opaque sessions hashed at rest; Secure/HttpOnly/SameSite cookies; expiry/rotation/revocation; CSRF token and Origin validation | Replay, logout, expired-session and cross-origin tests |
| Credential guessing | Strong password hashing, rate limits, generic identity errors; no passwords in logs | Rate-limit and log assertions |
| Prompt injection / excess authority | Treat model/retrieved content as untrusted; schema-validate calls; per-version tool grants and current revocation check; no implicit privilege changes | Adversarial unauthorized tool calls |
| SSRF / exfiltration | Deny-by-default destination allowlist; reject private/link-local/metadata addresses and redirects; validate DNS resolution and rebinding; egress gateway/firewall | IPv4/IPv6/redirect/DNS bypass tests |
| Secret leakage | Server-only encrypted secret references; deployment-managed key separation/rotation; redact API/events/logs/artifacts | Credential canary tests |
| Arbitrary execution | No user shell/code evaluation; bounded declarative mappings; constrained runtime identity and egress | Expression escape and scope tests |
| Cost/compute exhaustion | Atomic quotas/reservations; hard deadlines, output caps, concurrency and retry limits | Concurrent budget and timeout tests |
| Duplicate effects | Durable idempotency keys, leases/fencing, provider deduplication; disable unsafe automatic retries | Crash and duplicate delivery tests |
| Forged publication / stale edits | Editor role required; expected_revision; server revalidation and immutable published versions | Viewer denial and revision-race tests |
| Sensitive diagnostics | Sanitized structured errors; no secret values or private reasoning; retention/access policy for artifacts | Error and artifact access tests |
| Consequential writes | Disabled until explicit approval and tool-specific authorization exist; revoke grants immediately | Assert disabled paths cannot execute |

Role proposal: owner manages ownership/security; admin manages members/configuration; editor creates/versions/tests/runs definitions; viewer reads permitted definitions and redacted run metadata. Secret management restricted to owner/admin. Membership invitations and sensitive output permissions need explicit implementation policy; do not imply email invites exist before delivery ships.

Audit login/session events, membership changes, secret metadata changes, tool grants, publication, run submission/cancel/retry and denied consequential operations. Protect audit integrity and avoid storing sensitive payloads. Document restore procedures, dependency updates and environment separation before production.
