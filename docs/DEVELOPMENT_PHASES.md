# Development phases

Audit date: 25 October 2026. Status describes local functionality, not production certification. Avoid a single percentage: unfinished capabilities have very different scope.

| Phase | Audited state | Acceptance criteria still outstanding |
|---|---|---|
| 1 Architecture and foundation | Working locally | Maintain API contracts, module boundaries and decisions as features ship |
| 2 Identity and workspaces | Complete for local phase scope | Verified email, recovery, invitations, membership roles/removal, ownership protection, workspace creation/rename and session revocation implemented. Configure production SMTP before public use. |
| 3 Provider connections | Complete for reviewed local scope | Five provider connections, shared model capability/pricing profiles, safe catalog paging and saved-key refresh; 11 reviewed model IDs. Additional model/connector families remain later expansion. |
| 4 Agent builder and versions | Complete for local authoring scope | Guided primitive schema fields with advanced JSON preservation, tool contract inspection, shared publication checklist, output-token ceilings, immutable versions/compare/restore and viewer controls |
| 5 Agent harness | Complete for reviewed local scope | All five provider tool protocols, pinned read-only agent MCP grants and encrypted observed-run regression examples. Live provider acceptance and automatic paid evaluation batches remain expansion work. |
| 6 Workflow authoring | Complete for bounded local authoring and composition scope | Thirty direct steps/four agents, nested conditions, fan-out/merges, visual mappings, sequential For each loops and pinned subworkflow calls. Three workflow levels, 120 expanded steps/eight agent calls and twenty-item ceilings are enforced. General while-loops, richer expressions and long-lived orchestration remain expansion work. |
| 7 Durable execution | Complete for bounded local runtime scope | Encrypted scoped/item checkpoints, persisted child resource limits, claim fencing, safe recovery, classified local retries, explicit replay and workflow debugger implemented. Long-lived waits, advanced attempt history and production capacity isolation remain. |
| 8 Automation triggers | Complete for local interval/JSON webhook scope | Authenticated JSON delivery, event deduplication, persistent 60–86400-second schedules, pause/resume/archive, key rotation and recovery. Cron/calendar rules and provider-specific signed receivers remain expansion work. |
| 9 Tools and integrations | Local HTTP/MCP foundation complete; connector ecosystem partial | Fixed HTTPS actions, reusable tool credentials, read-only agent grants and durable write receipts implemented. OAuth, guided vendor connectors, private network access and more transport types remain. |
| 10 Hosted endpoints | Working locally | Public HTTPS hosting, capacity isolation and operational readiness |
| 11 Templates | Complete for local portable-pattern scope | Ten starters including a working child/batch pair, action patterns, previews/setup, private/workspace/public sharing and versioned JSON import/export. Imported dependencies must be connected in the target workspace. Marketplace curation remains expansion work. |
| 12 Usage and billing | Usage controls complete locally; billing partial | Shared transactional reservations, UTC daily budget/run limits and real usage UI implemented. Operator-owned plan ceilings, monthly entitlements, price updates and subscriptions remain. |
| 13 Teams and governance | Partial | Fine permissions, human approval, collaboration and audit export |
| 14 Quality and operations | Local release checks and restore rehearsal complete; production operations partial | Password-encrypted backup/isolated restore, worker-process checks, API readiness, HTTP smoke, security regressions and frontend checks implemented. Managed retention/WAL, key rotation, alerts, load tests, operator egress and external review remain. |

## Delivery order

Delivered: API actions/credentials, visual field mapping, execution debugging, portable action templates, bounded iteration/subworkflows and local restore verification. Next orchestration work: durable human approval and waits. Next connector work: guided GitHub actions, then Slack, building on the existing HTTP foundation; add OAuth only when its lifecycle can be tested. Implement each as a tested vertical slice with permission, failure and credential-revocation handling. Tenant-controlled workspace quotas now exist; add operator-owned plan ceilings before public multi-tenant hosting. See [loops and reusable workflows](learning/19-WORKFLOW-LOOPS-AND-SUBWORKFLOWS.md) for this completed phase and its verified limits.

## Scope and evidence

Published versions, credential checks, hosted bearer keys, local tools and restricted read-only MCP agents/workflows exist. Trigger nodes now have separate durable automation bindings. Tests must use an isolated PostgreSQL database ending in `_test`; local compile checks alone do not verify runtime behavior. Real provider/MCP/OAuth testing requires the corresponding configured service; no secrets should appear in test output.

Production work involving DNS, external accounts, billing providers and security review remains separate from locally verifiable code. Update PROJECT_STATUS.md with the actual checks and limitations after each delivered slice.
