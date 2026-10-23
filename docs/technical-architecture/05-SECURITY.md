# 05 — identity, workspace authority and tool safety

Security controls below are proposed acceptance requirements, not implemented guarantees. The initial private development deployment must not be represented as production-ready authentication or execution isolation.

## Authentication flow

FastAPI owns password authentication and sessions. Browser communicates through one origin: reverse proxy routes `/api/v1` to FastAPI and pages to Next.js. No browser bearer tokens in localStorage, no second Next.js session database and no cross-origin credential sharing.

1. Browser requests CSRF context. A short-lived signed/random pre-auth context plus synchronizer token protects registration/login; Origin must be allowed.
2. Register validates email/password, hashes password with Argon2id using a maintained library and calibrated parameters, creates identity, rotates pre-auth context into a session. Login uses generic errors and a dummy hash path for unknown users to reduce enumeration/timing differences.
3. Generate at least 32 cryptographically random bytes for session token. Store only token hash; session table owns user, idle/absolute expirations and revocation. Return opaque token cookie, never a JWT claim that independently grants workspace access.
4. Production cookie `__Host-ff_session`: Secure, HttpOnly, SameSite=Lax, Path=/, no Domain. Local HTTP uses an explicitly development-only cookie name/config; never silently weaken production cookie security.
5. Proposed idle expiry 12h, absolute expiry 7d. Throttle last-used updates to avoid writes on every poll. Rotate session on login, password/security change and privilege-sensitive reauthentication. Logout revokes server session and expires cookie; logout-all/password-change revokes other sessions.
6. Authenticated GET session returns a separate CSRF token held in browser memory; unsafe methods supply it in `X-CSRF-Token`. Validate Origin and token, including login/logout. SameSite alone is not the CSRF defense.
7. Server-rendered reads explicitly forward session to FastAPI, receive safe DTOs and use no-store caching. Browser cookie/session values never become client-component props or logs.

OWASP recommends strict session lifecycle controls and secure cookie handling; exact expiry and token choices above are FlowForge policy proposals. [OWASP session guidance](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html).

Rate-limit registration/login by IP and normalized identity with bounded counters; shared counters may use Redis. Auth endpoint rate-limit dependency failure returns temporary unavailable rather than unrestricted attempts. Do not log email/password bodies. Handle trusted proxy headers only from the configured ingress. Add email verification/reset delivery, password recovery tests, account abuse controls and domain/TLS configuration before public launch; local development can use registered accounts without pretending verification exists.

## Role model

Membership is evaluated for each API request; workflow/agent ownership alone does not give a user cross-workspace authority. Frontend role hints improve usability but cannot authorize anything.

| Operation | Viewer | Editor | Admin | Owner |
|---|---|---|---|---|
| Read definitions/version summaries | Yes | Yes | Yes | Yes |
| Read redacted run status/event metadata | Yes | Yes | Yes | Yes |
| Read sensitive artifacts/input/output | No | Yes | Yes | Yes |
| Create/edit/test/publish/run/retry | No | Yes | Yes | Yes |
| Cancel own active run | No | Yes | Yes | Yes |
| Cancel another member's run | No | No | Yes | Yes |
| Manage installed tools/provider credentials | No | No | Yes | Yes |
| Manage viewer/editor members | No | No | Yes | Yes |
| Grant/remove admin or owner | No | No | No | Yes |
| Change quota/security/ownership policy | No | No | No | Yes |
| Read audit/security metadata | No | No | Yes | Yes |

Settings support a common read-only view, with mutations separated by permission. Members list restricted to admin/owner initially. Editors have workspace-wide sensitive execution visibility; if pilot users need per-agent confidentiality, add explicit resource grants later rather than pretending this coarse role system supplies them.

API loads resource with workspace scope. Out-of-scope IDs return 404; recognizable forbidden action returns 403. Compound foreign keys also prevent tenant-crossing relationships. Privilege changes and last-owner checks are transactional; an admin cannot promote itself. Worker rechecks requester membership and current connection/tool revocation before each effect. Removing/disable requester stops future calls (`AUTHORIZATION_REVOKED`); cannot undo already dispatched effects.

## Tool Registry model

ToolDefinition is a workspace-approved installation of trusted server code. ToolVersion fixes handler revision, schemas, effect class, timeout, scope vocabulary, destination policy and retry safety. Registration chooses from installed handlers; uploading Python/JS or changing arbitrary handler names is forbidden.

MVP tools: bounded local JSON formatting/calculation without eval and a narrowly configured read-only HTTP JSON adapter only after SSRF controls pass. Do not ship unrestricted SQL, shell, filesystem or generic browser automation. External write tools stay disabled until explicit consequential-action approval and receipt/idempotency design is implemented.

Agent grants and direct workflow-tool grants are immutable subsets of tool policy:

`effective authority = installed handler policy ∩ current workspace allowlist ∩ immutable definition grant ∩ connection scopes ∩ current runtime restrictions`.

Version creation cannot grant authority absent from current policy. At each invocation validate:

1. Workspace ownership of step, tool, grant and connection.
2. Installed handler revision and available capability.
3. Current requester membership and revocation state.
4. Exact tool alias/version and schema-valid arguments; reject extra fields.
5. Requested operation, resource scope and destination restrictions.
6. Effect class/approval requirement and retry safety.
7. Remaining deadline, cost, call count and payload limits.
8. Redaction rules before persisting user-visible events.

Example: support agent gets `customer.read` for approved account lookup. A generated request to `customer.delete` is rejected even if instructions say it is urgent. An agent cannot widen its own tool grant by generating a new configuration.

## Credential storage and rotation

Credentials enter a dedicated admin/owner endpoint over TLS, are encrypted immediately with a maintained authenticated-encryption implementation, and return masked metadata only. Do not persist request bodies, decrypted values, credential headers or provider responses containing secrets. Encryption key mounted as a runtime secret is separate from ciphertext/backups and identified by key version. Never invent cryptographic primitives.

Only runtime workers requiring provider/tool access receive decryption capability; API needs encryption but credential-changing code must not expose a decrypt endpoint. With symmetric encryption, anyone holding the same key technically can decrypt; split API/runtime deployment key access via an envelope/secrets service before claiming cryptographic separation. MVP process-level key handling is a limited trust boundary, not hardware isolation. A compromised worker remains a serious threat, mitigated by narrow grants/egress and least-privilege DB roles.

Versions refer to connection ID, not credential value. Rotation activates a new encrypted generation, audit logs record generation ID and actor. Check revocation/generation before each new call; historical runs retain nonsecret generation metadata. Immediate revocation prevents future dispatch, but cannot recall an in-flight remote request. Frontend may display last-four masked hints only when safe; never allow secrets in graph JSON, exported configuration, Celery messages or command-line arguments.

## SSRF protection

Do not accept model/user-provided full URLs. Approved destination records are configured by platform/operator policy; workspace admins select/narrow them, not grant arbitrary public network access. Handler supplies operation-specific path/query schemas. Treat provider base URLs as fixed installed destinations; custom local/private model servers are out of MVP public deployment scope.

For every outbound request:

- HTTPS only, explicit approved host+port (443 initially), fixed path prefix and allowed method; reject credentials in URLs, fragments and unsafe path normalization. No proxy settings from ambient user-controlled environment.
- Resolve all A/AAAA answers; reject loopback, private, link-local, multicast, reserved and cloud metadata addresses, including IPv4-mapped IPv6 and encoded numeric variants. Deny a hostname if any usable answer is forbidden.
- Prevent DNS rebinding at connect time: use a transport/proxy that connects only to the validated resolved IP while preserving correct TLS SNI/hostname certificate verification. A check-then-default-client-second-resolution is insufficient.
- Disable redirects initially. If ever enabled, repeat all checks for every hop and never forward credentials to a different origin.
- Restrict destination-specific headers; only handler-controlled credential injection. Caller cannot supply Host, Authorization, proxy headers or arbitrary cookies.
- Limit DNS/connect/read/total durations, response bytes, decompressed bytes, JSON depth and pagination. No automatic remote schema/resource fetching.
- Enforce network egress outside the application in production: worker cannot reach metadata/internal administration networks; allow approved external services only. Compose networking by itself is not an outbound firewall.

These controls follow OWASP's allowlist and network-layer approach; exact destination records and transport implementation are required before enabling the HTTP tool. [OWASP SSRF prevention](https://cheatsheetseries.owasp.org/cheatsheets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.html).

## Security acceptance matrix

| Threat | Required evidence |
|---|---|
| Tenant ID guessing / foreign version reference | Two workspaces/users, all API methods and runtime grant paths denied across boundary |
| Session fixation/CSRF | Pre-auth rotation, missing/wrong CSRF, malicious Origin, expired/revoked session cases |
| Prompt injection | Malicious model/tool content cannot change authority, select unknown tool or leak another credential |
| SSRF | Loopback/private/metadata, IPv6/mapped addresses, rebinding, redirects and DNS answer mixtures denied |
| Cost exhaustion | Concurrent reservation race, unknown charges, retry multiplication and token ceiling tests |
| Unsafe replay | Worker loss/duplicate delivery cannot repeat non-replay-safe effect |
| Sensitive diagnostics | Canary secret absent from API errors, event history, logs, artifacts exposed to viewer and broker messages |
| Payload/code injection | Unsafe JSON Pointer keys/escaping, schema bombs and expression-like strings treated as data/rejected |
| Privilege escalation | Admin cannot create owner/admin, last owner preserved, removed member cannot dispatch future calls |

Use CSP/security headers, dependency updates and accessible error handling during UI slices. Do not render provider/model HTML as trusted markup. Audit publication, permission/role changes, credential metadata changes, run submit/cancel/retry, denied operations and unknown-outcome resolutions. Security logs use event IDs and safe metadata; logs are not a hidden copy of sensitive prompts.
