# Phase 4: guided agent authoring and publication checks

## What changed

The agent editor now offers guided input/output fields for simple object contracts. Users can add/remove primitive fields, describe them, choose required fields and edit string choices. Root descriptions and enums survive guided edits. Nested objects, arrays and advanced constraints stay in the JSON editor; the guided mode never flattens or discards them. For providers requiring every output property, a repair button marks all fields required.

Tool cards expose the local handler's argument schema and read-only permissions. Granting a tool still requires workspace approval and a model profile that supports local tools. The tool adapter can translate local handler arguments into the model protocol (for example, serializing JSON documents); these details are separate from the handler's contract. The sidebar now shows selected tool grants rather than always displaying “None”. Viewers can inspect contracts/history/checklists but cannot edit the configuration.

## Publication checklist

Save a draft, then choose **Check readiness**. FastAPI returns its saved revision, actionable errors, advisory warnings, publication status, execution support and configured output cap. Each issue links to its editor section. The checklist makes no provider call and creates no snapshot or run. It becomes hidden while local changes are unsaved.

The checklist and actual publication share one assessment function. This checks instructions, bounded schemas, connected/listed model, tool approvals/capabilities, tool-call allowance, positive budget and provider-specific output-contract restrictions. Publishing rechecks current state under the existing draft/connection locks and still rejects stale revisions. Readiness is a point-in-time assessment, not a guarantee against later key rotation, revoked grants, insufficient input-specific budget or provider outages. Setup-only models remain explicitly identified and cannot execute just because their configuration was published.

## Output and resource limits

New configurations include `limits.max_output_tokens`, from 16 to 4096, default 4096. It is a ceiling per model call. Both standalone runs and workflow agent steps take the smaller of this ceiling, the platform cap and the budget-derived allowance. The local-tool loop further reduces the allowance as it spends the run budget. Providers may include reasoning tokens in that allowance. Token limits and budget estimates do not guarantee the provider invoice.

The execution timeout is the run deadline including queue time. The current standalone model execution has a separate maximum of 30 seconds (25 seconds for a workflow agent step); the checklist explains this distinction when the configured deadline is longer. Retries, general checkpoints, provider tool parity and orchestration remain phases 5–7.

## Why versions stay immutable

The output ceiling lives inside the versioned configuration. Editing a draft or restoring an older version creates no mutation of published snapshots. Workflows keep using their pinned version. Historical stored configurations without the new key retain their original JSON and hash; their effective runtime cap defaults to the former platform limit of 4096. API configuration parsing also exposes that default. No data migration rewrites historical versions.

## Try it

1. Open an agent, or start from a quick start and select your connected model.
2. In **Schemas**, add fields and choose types. Open **Edit JSON** for nested structures or advanced validation constraints.
3. In **Model & tools**, review tool arguments and grant only approved tools the agent needs.
4. In **Limits**, set the output ceiling, iterations, tool calls, deadline and run budget.
5. Save and check readiness. Resolve required issues; review notes, then publish.
6. In **History**, compare or restore a version. Use the existing contract playground for example input/output validation and the run controls for supported live models.

## Validation

PostgreSQL tests cover checklist/publication agreement, aggregate missing-field errors, tool approval/call limits, viewer and tenant access, invalid token ceilings, snapshot preservation, restore, standalone worker enforcement and workflow execution of a pinned cap after restoring its agent draft. A legacy snapshot fixture verifies default behavior without changing the stored JSON. Frontend tests cover guided-edit preservation, refusal of unsupported schema structures, duplicate/unsafe field names and malformed JSON. All checks avoid paid provider calls.
