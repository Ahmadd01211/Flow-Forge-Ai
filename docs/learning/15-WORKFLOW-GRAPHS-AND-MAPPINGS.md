# Workflow graphs, joins and multiple agents

## What runs locally

Published workflows now support directed acyclic graphs with up to thirty nodes and four published-agent nodes. Fan-out, nested conditions and intermediate merges run through the same engine as local previews. Each graph has one input/webhook/schedule trigger and one final result. Every node must lie on a path between them, and cycles remain rejected.

The graph can fan out logically, while steps execute sequentially in a deterministic topological order. This keeps credential checks, shared budgets and cancellation manageable. The canvas does not imply concurrent provider calls. `max_parallel_steps` is retained for compatibility but does not enable parallel execution. Reconsider parallel scheduling when independent branch execution can coordinate reservations and claims reliably.

## Data flow

Select a step and open **Incoming field mappings**. Each connection can copy JSON Pointer fields from the earlier output into this step's input. For example `/ticket/id` → `/ticket_id` builds a flatter input object. An empty source means the complete upstream output; an empty target replaces the complete input. Without mappings, the complete output passes through.

Mappings on one connection must target separate fields. Duplicate, ancestor/descendant and whole-input/field combinations fail validation before publication instead of depending on mapping order. Existing unsafe-field protections remain in force. Mapped input is bounded to 64 KiB before the next step runs.

When only one incoming path is active, its mapped value passes through. With several active inputs, values are grouped under the source step IDs:

```json
{
  "classify": {"priority": "urgent"},
  "lookup": {"account_tier": "enterprise"}
}
```

The next step can read `/classify/priority` and `/lookup/account_tier`. Namespacing prevents one branch silently overwriting another. Node IDs, rather than editable labels, are stable mapping keys. Input objects are copied between steps so one branch cannot mutate another's input.

## Merge rules

**Merge paths** provides two choices:

- **Active paths** waits until every predecessor is resolved, then merges whichever paths ran. Use this to rejoin conditional routes.
- **Every connected path** runs only when every incoming path was active. If a predecessor is skipped, this merge is skipped as well.

Ordinary nodes with multiple incoming connections expose the same join behavior. The final Result always accepts active paths, preserving the existing conditional-result contract. A branch that is not chosen propagates a skipped state through its dependent steps, and traces now show those skipped nodes. If no active path reaches Result, the run fails with `RESULT_SKIPPED`; it does not report a successful null output.

Result references to a step that may be skipped still produce a configuration warning. Prefer incoming data or an explicit merge rather than referencing an optional branch directly.

## Agent budgets and uncertainty

Each agent node pins an immutable published version and rechecks credentials/tools before execution. Its allowance is the smaller of its own budget and the workflow budget remaining after previous measured model calls. Output tokens are recalculated from that allowance, and every call shares the workflow deadline. This prevents each agent in a pipeline independently spending the full workflow cap.

Before a model call begins, the run commits a possible-charge estimate for that call. On known success, usage/cost is added to the prior agents' totals and the estimate clears. If a later call fails ambiguously, earlier measured cost and the possible additional charge remain separate. The workspace usage guard counts both. Existing external-call markers still prevent an automatic replay of an uncertain provider/MCP operation.

## Verification and remaining scope

Integration tests cover nested true/false routing, active merges, skipped steps, fan-out mapping namespaces and collision rejection, two-agent output/token/cost accumulation, decreasing output allowances, and known-plus-uncertain charges after a later failure. A fresh Celery subprocess executes a fan-out/merge workflow through real Redis and PostgreSQL, covering independent model registration and the actual queue boundary.

No new migration was needed for this graph slice. Previously published linear/conditional graphs retain their output behavior; their new executions include richer skipped-step traces. Snapshot JSON/hashes are never rewritten. Subsequent slices delivered [scoped checkpoints](16-WORKFLOW-CHECKPOINTS-AND-DEBUGGER.md), [HTTP actions](17-HTTP-API-TOOLS-AND-TEMPLATE-FILES.md) and [bounded iteration/subworkflows](19-WORKFLOW-LOOPS-AND-SUBWORKFLOWS.md). General expressions and long-lived waits remain expansion work.
