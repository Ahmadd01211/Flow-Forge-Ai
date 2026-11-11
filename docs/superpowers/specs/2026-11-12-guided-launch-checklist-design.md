# Guided setup and launch checklist

Status: proposed design for review. The user selected this feature and requested an implementation plan; product implementation is not yet approved.

## Purpose

Help a non-coder take one agent or workflow from a recipe to a checked configuration, an inspected sample result and a published version. Keep the user in the existing editor and point directly to the next useful action. A successful sample demonstrates that sample only; it is not production certification.

## Existing behavior

- `workspace/task-start.tsx` and the template gallery already offer recipes and workspace-visible draft creation.
- `agents/agent-editor.tsx` owns saving, section reveal, server readiness and publishing. `TryPanel` runs the supplied current configuration, including unsaved settings, through the budgeted playground run API.
- `workflows/workflow-builder.tsx` owns save/validate, local preview, publish and published runs. External/model/approval/timer paths need a published run. `requiresPublishedRun` is the existing classifier and must remain authoritative.
- Backend agent readiness and workflow validation remain the sources of configuration rules and permission checks. Workspace-wide setup booleans are not evidence for a particular draft.

## Approaches

1. **Contextual editor checklist — recommended implementation choice.** Add a small reusable checklist and resource-specific adapters to existing editors. Reuse their controls and requests. Lowest duplication and no new persistence; sample progress resets on reload.
2. Separate setup wizard. Easier to isolate visually, but creates a second editor and synchronization problems when advanced settings change.
3. Persistent workspace launch dashboard. Supports cross-session evidence, but needs new aggregation, version matching and persistence contracts. Defer until the editor journey is proven.

The user selected the guided checklist concept. Choosing approach 1 and session-scoped sample evidence is the author's proposal for review, not an already approved user requirement.

## Experience

Recipe creation offers **Continue setup** into the existing editor; blank and previously saved resources get the same checklist. No recipe is required to use it.

Display four rows, with a named status, a short explanation and one useful action each:

- **Save your draft**: existing Save control; complete only for a saved, clean resource.
- **Check setup**: existing backend readiness/validation; configuration problems link to editor sections, skills, Integrations or Tools.
- **Try a sample**: open the existing test/input/result controls. Agent tests and local workflow previews appear before publication. Published-run workflows put this row after Publish and explain why.
- **Publish a version**: open the existing publication control; completion requires the current saved revision to be published. Publishing does not run anything.

Use **Sample succeeded**, **Sample failed**, **Still running**, **Waiting for approval**, and **Not tested in this session** where appropriate. Never describe publishing as execution or local preview as a durable run. Keep warnings visible even when publication is allowed. A setup-only model can remain publishable but the sample action explains that it cannot run.

Keep existing advanced controls available. Checklist actions reveal/focus those controls; they do not introduce a second save, publish or run path. Tests remain optional for publication under existing policy. No action starts a model call or external write merely by mounting, navigating or checking setup. The existing explicit Run/Send click and cost/action guidance remain required.

## State and evidence

No database migration, backend endpoint, localStorage progress record or new dependency in this slice.

The pure checklist model consumes normalized facts from each editor; it does not reproduce provider, tool or graph validation. It emits display rows and symbolic action IDs, never executable URLs from API messages.

Evidence belongs to one resource, one submitted configuration key, one submitted input and one request ID. The parent accepts only the latest attempt for its current configuration. Editing any submitted definition field invalidates prior success; saving identical configuration does not. Graph positions may conservatively invalidate workflow evidence in this first version. A later failed attempt supersedes earlier success. Late responses from an older request/configuration cannot restore a completed row.

The sample result refers to its submitted input, even if the input form has since been cleared or edited. Keep the original result/input visible in existing result controls. A new submission replaces checklist evidence. Sample input changes alone do not rewrite historical evidence or imply that the new input has been tested.

Published workflow evidence also records the submitted version ID; it only completes the row when that version matches the current publication and the editor is clean. Queued/running/waiting/unknown states never count as success. Polling expiry links to the existing run detail, without inferring failure or completion.

On reload, sample evidence resets to **Not tested in this session**; existing execution history remains available. Publication state may be restored from existing version props. On a hidden-to-visible tab transition, mark setup unchecked and clear active checklist sample evidence, while retaining outputs in the existing result controls. This conservative reset covers connection/skill/tool changes made elsewhere without pretending to detect them. Recheck uses existing endpoints; it never saves or spends money automatically. Old outputs remain historical evidence, not evidence that changed dependencies still work.

Readiness responses are scoped to the saved configuration/request. Dirty drafts show **Save and check setup**; stale or failed responses never show passed. This does not prohibit the existing agent test of unsaved settings: its evidence describes those submitted settings and remains valid after saving identical content. Unauthorized users see explanations and read-only links, with mutation actions unavailable. Backend authorization remains decisive.

## Design check

An independent builder check found no material unanswered implementation questions. Contextual placement, session-only evidence and conservative tab-return invalidation remain author-proposed choices for user review.

## Module boundaries

- `frontend/src/features/launch/launch-model.ts`: normalized types, deterministic configuration key and pure step derivation.
- `frontend/src/features/launch/launch-checklist.tsx`: accessible list and action rendering, no fetching or mutation.
- Agent editor/TryPanel: adapt existing readiness, revision and test lifecycle; emit bounded metadata, never copy run output into the checklist.
- Workflow builder: adapt existing validation/preview/publish/run states; preserve branch, join and authorization semantics.
- Template handoff and start page: route users to the shared journey without introducing a second creation action.

## Acceptance and review focus

1. A local-only recipe reaches preview without a provider prerequisite.
2. An external workflow explains publication-before-test and never reports preview success as a full-run success.
3. Editing during an in-flight test or receiving responses out of order cannot produce stale green completion.
4. Failed checks, revoked dependencies and setup-only models remain visibly unverified or blocked; publishing and runnable are distinct.
5. Viewer roles, blank drafts, unknown issue codes, restored published versions and pending approvals have useful states and safe actions.

Keyboard users can activate every available action and reach the revealed control. Status is textual, not color-only. The list stacks on narrow screens and uses existing CSS tokens/Lucide icons. Final manual checks cover one agent, one local recipe and one published-run workflow; real provider acceptance uses the user's own key.

## Boundaries

This design excludes document knowledge bases, OAuth, new connector families, billing, public deployment and historical test aggregation. It adds no new publishing restrictions and makes no claim that configuration checks prove real-provider access or output quality.
