# Task 4 report: recipe setup handoff

Status: implemented; focused verification passed. Controller owns integrated verification/runtime smoke.

## Delivered

- Changed the gallery success link to **Continue setup** on the existing agent/workflow editor route with a URL-encoded `recipe` query key. Uses instantiate `template_key`, falling back to the selected recipe key for compatible responses. No second create button or automatic navigation/run/publication. Copied-skill review/publication and library links remain.
- Added the first Start choice **Try without a model**, linking to `templates?focus=remove-duplicates`, and a matching gallery badge. Only the known built-in workflow key without user-template visibility receives the badge; labels/category do not classify arbitrary templates as local.
- Inspected `backend/app/modules/templates/{router,practical_starters,action_starters}.py`: instantiate creates a saved workflow from name/description/graph and returns template_key; GET detail already supplies optional sample_input/expected_result. Remove duplicates source sample has Ada, Lin and a later Ada email; expected output keeps first Ada and Lin, count 2/removed 1. No new endpoint/storage/dependency needed.
- Added a small tested metadata helper. It rejects absent, multiple, path/query-like, overlong keys; validates the template kind and optional object sample/string expected fields; catches unavailable/private/deleted/malformed metadata. It returns only sample/expected data, never graph/config.
- Both server editor pages optionally load those examples via the existing GET detail endpoint. Existing resource loading and workflow session canEdit wiring remain. Fetch failure cannot break editor loading.
- Workflow input initializes from the source sample or an empty object with a safe-input instruction, replacing the old universal text-cleanup sample. Expected source example appears beside the form. Graph/settings initialization is untouched.
- Agent TryPanel optionally initializes chat message, primitive fields and JSON form once using React state initializers. Prop refreshes do not overwrite user edits. Expected source example is visible; a sample-free recipe requests safe input. No request runs on initialization.
- Updated manual guide/status: local demo handoff, agent/skill setup, session-only evidence and reload reset, post-edit rechecks, publication separate from runs, external workflow published-agent/API-tool setup order and explicit potentially paid/external Run. Signed-in GUI/live provider/API/MCP acceptance is explicitly unperformed.
- Used UI Styling and UI/UX Pro Max guidance with existing panel/button/badge/field components and tokens; no redesign.

## RED evidence

Updated gallery/start tests failed meaningfully before implementation: **7 failed, 9 passed**. Failures covered missing Continue setup links/query, no-model prominence and explicit sample-free handoff instructions. The metadata helper suite failed with the module absent before implementation. Existing API/route tests were retained and updated for the approved query handoff.

## Final focused verification

From frontend:

```text
npx vitest run src/features/templates/template-gallery.test.tsx src/features/templates/recipe-handoff.test.ts src/features/workspace/task-start.test.ts src/features/workspace/task-start-model.test.ts src/features/workflows/workflow-builder.test.tsx src/features/agents/try-panel.test.tsx --maxWorkers=2

Test Files  6 passed (6)
     Tests  60 passed (60)
```

`npm run typecheck`: exit 0.

Scoped `npx eslint` on every touched TS/TSX file (gallery, helper, start/model, both editor pages, AgentEditor, TryPanel, WorkflowBuilder and related tests): exit 0, no diagnostics.

`git diff --check`: exit 0 (only normal Windows LF/CRLF notices).

Coverage includes existing-route agent/workflow Continue setup, attached-skill links, exactly one instantiate POST, source sample-free imported recipe instructions, known-key-only local prominence, invalid/missing/failed/malformed metadata fallback, workflow example initialization without requests/graph saves, agent form/chat initialization and preservation of user edits without auto-run.

## Verification limits and remaining ownership

No full npm test/lint/API/build was run by this implementer, per the ownership refinement. Controller runs those once after review; root runs HTTP smoke. No backend behavior/contracts changed. No signed-in GUI, real credential/provider generation, API external action or live MCP approval acceptance was performed. Manual boxes remain unticked and must reflect actual observed outcomes.

Recipe metadata is an explicit URL handoff convenience, not persisted progress or binding. Reload can initialize its sample again while launch evidence still resets. Missing recipes remain normal editors with user-entered sample input. Expected examples describe source intent; they are not assertions of an executed or correct result.

Protected connector files, `.agents/`, and `frontend/next-env.d.ts` were not modified or staged by Task 4. Existing uncommitted generated/local differences remain.
