# Bounded loops and reusable workflows

## What is complete in this phase

The visual builder has two new nodes: **Subworkflow** and **For each item**. Both call an exact published workflow version in the same workspace. Drafts are never execution targets. Publishing the parent pins the child version's content hash; a newer child version does not silently change an existing parent.

This phase includes authoring, dependency validation, local previews, durable execution, per-item evidence, cancellation, recovery, shared budgets, private template portability and a working pair of starter templates. Human approval waits, arbitrary while-loops, cross-workspace calls and general expression/code execution are outside this slice.

## Learn by running the paired templates

1. Open **Templates** and create **Prepare a customer profile**. It only maps local fields, so no provider key or API credential is needed. Publish version 1.
2. Create **Batch customer profiles** from Templates.
3. Select **Process customers** in the canvas or Steps view. Choose the published customer-profile version. If you published it in another tab, use **Refresh published versions** without losing your parent draft.
4. Keep the list field `/items`, the **Item and index** input mode and a five-item maximum. Inspect the child's input/output contracts before connecting other data.
5. Put the following sample in the builder's **Input JSON**, then Preview. Publish and Run to record durable evidence.

```json
{
  "items": [
    {"name": "Ada", "email": "ada@example.com"},
    {"name": "Lin", "email": "lin@example.com"}
  ]
}
```

The first invocation receives `{"item":{"name":"Ada","email":"ada@example.com"},"index":0}`. The second receives index 1. The loop returns an object with an ordered `items` array containing child outputs and a `count` of 2. Empty lists return `{"items":[],"count":0}`. Nothing is truncated when a list exceeds its maximum: the step fails before the first child.

**Item object itself** is useful when an existing child already accepts the item shape, for example `{"ticket":"A"}`. This mode requires every item to be an object; the envelope mode can carry scalar items if the child's input contract permits them. The whole parent input is not implicitly copied to each child. Put required context in the item or use an explicit mapping/transform.

Every generated child input is checked against the child's published input schema before any item runs. This avoids predictable partial actions caused by a malformed later input. It cannot predict failures inside a child, output-contract violations or outages; earlier items can have completed when a later one fails. Loops stop at the first failure.

## Limits are enforced before execution

| Boundary | Local release limit |
|---|---|
| Nodes in any one graph | 30, with at most four direct agent nodes |
| Loop item ceiling | 1–20 configured; an actual list may be empty |
| Workflow levels | Three, counting root, child and grandchild |
| Worst-case expanded work | 120 steps and eight agent calls |
| Dependencies inspected | 24 distinct published versions, 400 inspected graph nodes |
| Stored checkpoint payloads | 2 MiB per run, including encryption overhead |
| Per-step input/output | Existing 64 KiB bounds; loop result stays within the same output bound |
| Run deadline | Parent's configured timeout, capped at 15 seconds for local-only work or 30 seconds when external work appears anywhere in the dependency tree; queue time counts |

Worst-case counts include every branch and every allowed loop item. A parent with three nodes calling a three-node body up to five times has eighteen expanded steps: three parent steps plus fifteen child steps. Nested loops multiply their body counts. The validation panel exposes these totals, and publication/admission reject oversized compositions. Merely changing a node's label cannot bypass a bound.

Self/ancestor calls are rejected even if they reference an older version of the same workflow. Cross-workspace version IDs remain unavailable. Child credentials, tool approvals and current provider capabilities are checked recursively before admission and execution; revoking a nested API tool blocks the root before a network call.

## One run owns all resource use

Children execute inside one root run rather than creating independent Celery jobs. There is one workspace reservation and accepted-run count. Model tokens, known cost and uncertain possible charges accumulate on that root. A root containing only a Subworkflow node still reserves a model budget if any descendant calls an agent.

Each invocation is bounded by the smaller of the parent's remaining allowance, the child's own configured budget and the agent's own limits. Child deadlines also fit inside the parent deadline, the calling node's policy and the child's timeout. Resource scopes are saved in encrypted checkpoint metadata. Recovery restores their original ceilings/deadlines instead of adding a new budget or timeout after a worker restart.

Children are sequential. This avoids surprise bursts of API writes and keeps the existing single-run external-call marker meaningful. A scheduler/parallel child-job design is a realistic alternative when throughput or long-lived child workloads demand it, but it would require leases, independent cancellation, fan-in and reservations across jobs. Those costs are unnecessary for this bounded release.

## How recovery knows which item finished

Each checkpoint keeps an internal stable identity plus a human-readable scope such as `batch[1] / profile`. A second loop iteration cannot overwrite the first one's input or output. A child records its parent step, item index and published version. The execution screen presents item numbers starting at one, while input JSON uses zero-based indexes.

Checkpoint sequences are allocated under the root run's lock when a record is first created. They are not derived from the current traversal length: after a restart, the runtime may skip an entire completed subtree. A repeated Celery delivery cannot claim a completed/running run again, and stale worker claims cannot write evidence.

If a worker dies safely after item one, recovery reuses its completed checkpoints and continues item two. If it dies while an external request is in flight, the existing uncertain-outcome rule prevents automatic retransmission. The parent retains earlier item receipts so an operator can inspect the target service before choosing a replay. **Replay starts a new root run and can repeat completed actions**, so it requires acknowledgement for external descendants too.

Cancel, role removal, deployment revocation and deadlines stop future work at the existing execution boundaries. In-flight requests cannot be recalled. Local previews are allowed only when the entire selected dependency tree is local; nested agents/API/MCP tools require a published run. Standalone node tests follow the same rule.

## API and storage changes

- `GET /api/v1/workspaces/{workspace_id}/workflows/call-options` returns executable published choices, schemas, limits and expansion counts. `exclude_workflow_id` hides self versions in the editor. Viewer members may read choices but cannot submit writes.
- Graph node kinds now include `subworkflow` with `version_id`, and `for_each` with `version_id`, `source`, `input_mode` and `max_items`. `graph_hash` is server-pinned on publication.
- Step responses add `definition_node_id`, `scope`, `parent_node_id`, `iteration_index` and `workflow_version_id`. Existing step URLs continue to use the stored unique `node_id`; legacy records still display correctly.
- Migration **0022** increases the checkpoint sequence bound from thirty to 120. Existing versions and encrypted records are not rewritten. Downgrade refuses to discard expanded history.
- Export/import removes private child bindings while preserving a loop's list path, mode and maximum. Users must select a published workflow in the receiving workspace.

`composition.py` contains contracts/resolution and local composition. `runner.py` adds durable orchestration using the existing agent/MCP/HTTP adapters. `checkpoints.py` owns scope identities, fencing and persisted resource bounds. This keeps feature logic in the modular monolith without adding a new queue, workflow engine or speculative plugin layer.

## Verification

PostgreSQL/Redis tests cover both input modes, empty/oversized/malformed lists, immutable version pinning, private-workspace boundaries, recursion/depth/expansion rejection, nested model reservations and diminishing budgets, revoked service grants, cancellation after a receipt, safe recovery without resending a completed item, uncertain external calls and explicit replay acknowledgement. The paired templates are instantiated, bound, published and executed in tests.

The real local app also completed a two-customer batch through Celery and stored all nine scoped checkpoints. Preview and durable outputs matched by JSON value rather than object-key order. No paid model or external service was called during that exercise. The editor and per-item evidence were reviewed in a disposable local workspace. Cleanup revokes its sessions and test password, discards temporary login material, and preserves published audit history.

Browser review also caught a server/browser timezone hydration mismatch. A shared timestamp component renders the same explicit UTC fallback on the server and first client render, then switches to the browser's local time. The same correction is applied to agent history, runs, automations, deployments, settings and usage. Timestamp tests cover the stable server snapshot and invalid values. The overview uses actual recorded run/usage data in place of an obsolete runtime placeholder.
