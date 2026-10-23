# Development phases

Audit date: 23 October 2026. Status describes local functionality, not production certification. Avoid a single percentage: unfinished capabilities have very different scope.

| Phase | Audited state | Acceptance criteria still outstanding |
|---|---|---|
| 1 Architecture and foundation | Working locally | Maintain API contracts, module boundaries and decisions as features ship |
| 2 Identity and workspaces | Complete for local phase scope | Verified email, recovery, invitations, membership roles/removal, ownership protection, workspace creation/rename and session revocation implemented. Configure production SMTP before public use. |
| 3 Provider connections | Complete for reviewed local scope | Five provider connections, shared model capability/pricing profiles, safe catalog paging and saved-key refresh; 11 reviewed model IDs. Additional model/connector families remain later expansion. |
| 4 Agent builder and versions | Complete for local authoring scope | Guided primitive schema fields with advanced JSON preservation, tool contract inspection, shared publication checklist, output-token ceilings, immutable versions/compare/restore and viewer controls |
| 5 Agent harness | Partial | Agent-initiated MCP, provider tool-call parity, evaluations |
| 6 Workflow authoring | Partial | Multiple agents, general joins, bounded iteration, subworkflows, visual mappings |
| 7 Durable execution | Partial | Step checkpoints, policy-driven retries, explicit replay, richer debugger |
| 8 Automation triggers | Incomplete | Trigger nodes only; authenticated webhook delivery, persistent interval schedules, pause/resume and recovery remain. Work deferred while phase 2 is completed. |
| 9 Tools and integrations | Partial | Secure HTTP actions, reusable API credentials, OAuth, first service connectors |
| 10 Hosted endpoints | Working locally | Public HTTPS hosting, capacity isolation and operational readiness |
| 11 Templates | Partial | More useful end-to-end templates, import/export, sharing |
| 12 Usage and billing | Partial | Workspace reservations/quotas, provider price updates, subscriptions |
| 13 Teams and governance | Partial | Fine permissions, human approval, collaboration and audit export |
| 14 Quality and operations | Partial | Backup/restore exercises, alerts, load tests, network egress policy, external security review |

## Delivery order

Finish triggers first, then HTTP actions and credentials, then visual data mapping and execution debugging. Use those foundations for a lead-intake template: incoming event → validation → agent classification → approval → service action → notification. Implement each connector as a tested vertical slice with permission, failure and credential-revocation handling. Expand graph execution before adding loops or multi-agent orchestration to the palette. Add workspace quotas before public multi-tenant hosting.

## Scope and evidence

Published versions, credential checks, hosted bearer keys, local tools and restricted read-only MCP workflows exist. Trigger node types were previously added without automatic dispatch; that was not completed automation. Tests must use an isolated PostgreSQL database ending in `_test`; local compile checks alone do not verify runtime behavior. Real provider/MCP/OAuth testing requires the corresponding configured service; no secrets should appear in test output.

Production work involving DNS, external accounts, billing providers and security review remains separate from locally verifiable code. Update PROJECT_STATUS.md with the actual checks and limitations after each delivered slice.
