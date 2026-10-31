# HTTP API tools and portable templates

## What we built

Tool Registry now has an **HTTP API tools** section. An owner/admin approves one fixed HTTPS endpoint, method, input/output contracts and header credential. Builders select that approved tool in a workflow. Agents can receive only explicitly reviewed read-only GET grants. The server pins each grant's contract hash and credential generation when publishing.

One generic adapter is appropriate for this release because many service actions share the same JSON request/response pattern. Separate vendor SDKs would duplicate credential handling, permissions and failure logic. We should introduce a dedicated connector when a service needs OAuth, pagination, dynamic resource discovery, file transfer or signature verification. We should introduce an egress proxy before public hosting or supporting private-network destinations.

## Try a read-only tool

1. Open **Tool Registry → Add API tool** as an owner/admin.
2. Choose GET and enter a fixed public HTTPS endpoint. Query strings, credentials in URLs and arbitrary per-call headers are not supported.
3. Select no authentication, bearer token or a dedicated API-key header. Put the credential only in its password field.
4. Define the input contract. GET input supports scalar query values, not nested objects/arrays. Mark the endpoint read-only only after reviewing its behavior.
5. Approve the destination. Saving checks its network destination, but does not claim its credentials work.
6. Confirm an external test and inspect the response. Tests are limited to twenty per workspace per minute.
7. In an agent's **Model & tools**, select the approved API tool, save and publish. The model never receives its credential.

HTTP results have this envelope:

```json
{"status_code":200,"body":{"id":"customer-123","status":"active"}}
```

An output contract validates this whole envelope. Match the actual response shape of your service. Keep input contracts narrow so a model cannot request arbitrary fields supported by a powerful API.

## Try a write action

Approve POST, PUT, PATCH or DELETE as an action. Add **HTTP API** from the workflow palette, choose the approved tool and map incoming fields to its input contract. Publish and run the workflow; write actions do not use the disposable node-test path. Open **Executions → Workflows** to inspect the step's encrypted input, result or failure.

For example, a GitHub issue action can use a fixed repository URL `https://api.github.com/repos/OWNER/REPO/issues`, POST, a bearer credential restricted to that repository, and input containing `title` and `body`. A fine-grained token needs Issues write permission. This is a configuration recipe, not a live-tested dedicated connector; review the [official GitHub issue contract](https://docs.github.com/en/rest/issues/issues?apiVersion=latest).

A Slack message action can use `https://slack.com/api/chat.postMessage`, POST, a bearer bot token with the appropriate channel permissions, and `channel` plus `text` input. Validate `body.ok` as `true` in the output contract: an HTTP 200 response alone does not prove that Slack accepted a message. See [Slack's method contract and permissions](https://docs.slack.dev/reference/methods/chat.postMessage/). Existing service credentials are supplied by the workspace admin; FlowForge does not install an app or perform OAuth for these recipes.

The three new starters are **Webhook to API action**, **Scheduled API digest** and **AI priority routing with action**. Preview a template for setup steps and sample JSON. Their service/agent bindings are intentionally blank. They cannot publish until you choose your workspace's approved dependencies. The digest expects a response containing `body.items`; adjust the filter for another response shape. AI routing is automated and has no human approval wait yet.

## Why writes do not retry automatically

A timeout can mean the service received the action but the receipt was lost. Repeating it could create two tickets or send two messages. A durable external-call marker is committed before a request, and cleared only after its result is checkpointed. A worker failure during that interval leaves an uncertain outcome, and recovery refuses to resend it. After inspecting the target service, a user may explicitly replay the whole run with an idempotency key and an external-effects acknowledgement. Replay can repeat earlier completed actions; it is not an exactly-once guarantee at a remote service.

Use a service-supported idempotency field in the fixed body contract where available. A generic HTTP adapter cannot invent an idempotency guarantee for a target API.

## Network and credential boundaries

- Public IPv4 DNS names on HTTPS port 443 only. Every returned IPv4 address is checked. One approved address is pinned to the actual TCP connection, with the original Host and TLS certificate identity. HTTPX supports this through its documented [SNI extension](https://www.python-httpx.org/advanced/extensions/#sni_hostname).
- Resolver work has a three-second deadline, four threads and eight occupied/queued slots. Timed-out OS lookups retain their slot until they finish, preventing an unbounded resolver backlog. The request's remaining deadline also bounds DNS work.
- No redirects, environment proxies, user-controlled routing headers, IPv6-only targets, cookies or compressed bodies. Input/output are bounded at 64 KiB, GET queries at 4 KiB, network work at twelve seconds and the effective workflow deadline may be lower.
- Credentials use authenticated encryption bound to workspace/tool/generation. They are never returned by listing or publishing. Rotation and revocation invalidate old grants. Common raw credential echoes are redacted before recording/returning output; this is not protection against a malicious destination encoding the secret. Admins must approve trustworthy services and minimum-permission credentials.
- Credentials can be reused by multiple agent/workflow versions through the approved tool. Each destination/method is a separate permission boundary; there is no global unrestricted credential vault.
- Existing work is checked after queueing and between steps. Removing/demoting a requester stops future work. Deployment runs also require an active deployment and a creator with an admin role. Already in-flight remote work cannot be recalled.
- Model budgets do not cover target API fees. The service may charge even when FlowForge cannot verify a response.

## Export and import

**Templates → Export JSON** downloads a version-one `flowforge-template` package. Import creates a private saved template, not a published agent or a running workflow. Input is size-bounded, parsed against supported schemas, and graph structure is validated. Connections, HTTP/MCP grants and published agent bindings are cleared again on import. Local tool keys still need approval in the receiving workspace.

Review instructions, descriptions and fixed values before sharing: an application cannot reliably detect a secret pasted into arbitrary prose. Never use instructions to store credentials. Imported packages are data, not executable code; FlowForge does not execute arbitrary Python/JavaScript from a template.

## Evidence and reconsideration

Tests cover URL/DNS restrictions, redirect/size/content failures, TLS routing, encryption, role/CSRF/tenant boundaries, immutable grants, rotation, provider revocation between model turns, workflow action receipts and duplicate delivery. Starter graphs exercise both AI routing branches using controlled dependencies. Package tests cover private import, binding removal, malformed versions and invalid graphs. No live GitHub, Slack or paid provider action was performed.

Next revisions should add service-specific error summaries and rate-limit handling without replaying writes, scoped custom headers where genuinely needed, OAuth and an operator-owned egress layer. Loops, subworkflows and approval waits remain separate orchestration work.
