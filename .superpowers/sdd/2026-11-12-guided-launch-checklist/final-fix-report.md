# Final review fix report

Base: `c0b4d57` on `feature/local-release-continuation`.

Scope: the three important findings and one HTTP tool copy finding from final review. No backend or API contract changes.

## Changes

- Agent sample identity now resets on actual submitted definition changes. Editing A to B and back to A cannot restore completed evidence or accept an old pending completion. Existing TryPanel output remains visible. Saving identical submitted settings retains the evidence.
- Workflow status polling failures after an accepted POST now retain the accepted run ID and report unknown. Actual terminal states and preacceptance failures retain their existing handling. The durable debugger link remains available.
- The agent page keys the editor by resource ID. AgentEditor recognizes acknowledged saves across revision refreshes, preserving sample evidence, historical output and unsubmitted sample input. A changed external definition reconciles the saved baseline and revision; clean drafts adopt its fields and schemas, while dirty drafts retain local edits and display a server-change notice. External definition changes invalidate active setup/sample evidence.
- HTTP tool workspace-access copy distinguishes active from revoked access.

## RED evidence

Command from `frontend`:

```text
npm test -- src/features/agents/agent-launch.test.tsx src/features/workflows/workflow-builder.test.tsx
Test Files  2 failed (2)
Tests       7 failed | 35 passed (42)
```

Observed expected failures before implementation:

1. Completed agent sample becomes succeeded again after definition edit/undo and setup recheck.
2. Pending agent completion is accepted after definition edit/undo and setup recheck.
3. Real agent page revision refresh drops the sample, history and unsubmitted form state after saving the same submitted configuration.
4. External restored revision drops historical output at the page remount boundary.
5. External server revision silently replaces unsaved instructions. A targeted rerun confirmed the received value was the server instructions instead of the local unsaved instructions.
6. Accepted queued workflow run followed by a rejected status request lacks the unknown state.
7. Accepted running workflow run followed by a rejected status request lacks the unknown state.

The direct AgentEditor identical-save refresh case passed before the fix and remains a preservation control. Initial test-selector/type-option mistakes were corrected before the final checks; they did not motivate production changes.

## GREEN evidence

```text
npm test -- src/features/agents/agent-launch.test.tsx src/features/workflows/workflow-builder.test.tsx
Test Files  2 passed (2)
Tests       42 passed (42)

npm test -- src/features/agents src/features/launch src/features/workflows/workflow-builder.test.tsx src/features/workflows/selected-path.test.tsx src/features/tools/http-tool-registry.test.tsx
Test Files  11 passed (11)
Tests       71 passed (71)

npm run typecheck
tsc --noEmit
Exit 0

npm run lint
eslint .
Exit 0

git diff --check
Exit 0
```

Focused tests cover the changed editor/page boundary, TryPanel, schemas, checklist model/rendering, selected workflow paths, builder state and HTTP registry. No full suite or production build was run in this wave; the root agent owns final integrated verification.

User-local `.agents/` was untouched and remains untracked. `frontend/next-env.d.ts` was untouched, preserving both original `.next/types` imports. This report is UTF-8 and is committed with the owned fixes.
