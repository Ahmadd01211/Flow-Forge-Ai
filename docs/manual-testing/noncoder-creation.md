# Noncoder creation: manual GUI checklist

Prepared from source on 11 November 2026. **Not yet executed in the GUI: final walkthrough belongs to the user.** Tick boxes only after observing the result. Use `http://localhost:8080`, sign in and select a workspace. Replace `<workspaceId>`, `<agentId>` and `<workflowId>` below with the IDs in its URLs. Use an owner/admin account for provider setup and an editor or above for draft creation. Use safe sample data: drafts and copied skills are workspace-visible.

## Discover, preview and create

- [ ] Open `/w/<workspaceId>/start`. Confirm **Choose what to build**, **Browse task recipes**, **Preview support triage**, **Create a blank agent**, and **Open workflows**. Choose **Browse task recipes**, reaching `/w/<workspaceId>/templates`.
- [ ] In **Search recipes**, enter `I want to draft a customer reply`. Confirm **Customer reply draft** matches and has **Recommended**. Set **Category** to **Support** and confirm the match remains. Clear search, select **Productivity**, and confirm **Meeting action items** is recommended. Search `zzzznomatch` and confirm the no-results message; restore **All categories** and clear search.
- [ ] Click **Preview** on **Customer reply draft**. Read **Expected result**, **Required setup**, **Skills copied as editable drafts**, **Sample input**, and expand **Recipe instructions and steps**. Confirm the copy explains workspace visibility, review/publication, and possible provider charges. Browsing and previewing must not create an agent or submit a model run.
- [ ] Choose **Close preview**; keyboard focus should return to its Preview button. Preview it again, then choose **Create workspace draft**. Confirm **Workspace draft created: Customer reply draft**, the unpublished/unrun status, links for both attached skills, and **Open agent editor**. Creation should leave you at this handoff, without automatically testing or publishing.

## Review skills, connect a provider and test an agent

- [ ] Open each **Review attached skill** link (retain the handoff or its agent-editor link in another tab). Each opens `/w/<workspaceId>/agents/skills/<skillId>`. Review **When should an agent use it?**, **Instructions**, **Examples**, and **Tools this skill needs**. Customize Brand voice to your actual guidance, especially example promises/policies. Use **Save** for edits and **Publish** for each skill. Confirm **Published**, a version number and a Versions entry. `/w/<workspaceId>/agents/skills` should list both copies.
- [ ] Open `/w/<workspaceId>/integrations`. Even with no active provider, confirm **Connect a model provider**, **Choose provider**, and **Verify API key** are available. Choose your provider in **Model provider**, enter your own credential in its API key field, and choose **Verify key**. Keep the key in this interface; never put it in the checklist or chat.
- [ ] On successful verification, confirm the key-verified notice and **Choose a model**. Use **Search available models**, select a runnable model, review capability/pricing information and choose **Save default model**. **Show models for setup only** exposes unsupported listings; those are not generation acceptance. Use **Refresh models** without re-entering the saved key and confirm the list refreshes. Switching providers must show that provider's own connection/model state.
- [ ] For a previously unconnected provider, a verification/listing failure must show an error without claiming the provider is connected. A failed saved-key refresh should preserve the prior catalog/default and connection. Record only the provider name and safe error text. Resolve access/billing/model availability with your own account before the real test. Verification/catalog refresh alone does not confirm generation access or billing capacity.
- [ ] Return via **Open agent editor** to `/w/<workspaceId>/agents/<agentId>` (reload after provider/skill changes). Open **Brain**, choose the connected provider and a model marked **Live runs**. Open **Skills** and confirm both copied skills remain attached and display published versions. Review instructions, input/output fields and run budget; choose **Save** if changed.
- [ ] In **Try your agent**, fill `customer_message` with `Hello, could you let me know the shipping status of my order?` and `brand_guidelines` with `Use a clear, warm tone. Ask for an order number when details are missing.` Choose **Run it**. This submits a real budgeted provider run and can incur charges. Check that the output has `draft_reply` and `needs_human`, requests missing information and invents no shipping status. This recipe drafts text; it sends no customer message.
- [ ] Open **Trace** on the result to `/w/<workspaceId>/executions/<runId>`; inspect recorded outcome/usage. A failed run is not accepted generation. Record safe error details if needed. In the editor choose **Publish**, resolve readiness issues, then **Publish version**. Confirm the agent's Published version status. Publication and testing are separate actions.
- [ ] If a skill is edited again, **Save** and **Publish** a new skill version; reload the agent, review readiness and republish the agent to update its pinned skill version. Existing published agent versions retain their pins.

## Local workflow preview and durable run

- [ ] Return to Task recipes. Search `text cleanup`, **Preview** **Text cleanup**, **Create workspace draft**, then **Open workflow editor**, reaching `/w/<workspaceId>/workflows/<workflowId>/edit`.
- [ ] Choose **Validate** (or **Save & validate** after edits). In **Draft preview** set **Input JSON** to `{"text":"Hello world","find":"world","replacement":"team"}` and choose **Preview**. Confirm **Output JSON** is `{"text":"Hello team"}` and step statuses appear. This uses a local approved tool, needs no provider and creates no durable full-run record.
- [ ] Choose **Publish** after successful validation; confirm **Published version ready**. With the same Input JSON, choose **Run**. Confirm a durable run ID/state and follow **Open durable step debugger** to `/w/<workspaceId>/executions?kind=workflows&runId=<runId>`. Inspect persisted step evidence/output. A publish by itself must not submit a run; unsaved edits disable Run until saved/published again.
- [ ] For a publication-required example, preview **Review and release** in Task recipes and copy its **Sample input**. Create its workspace draft and open the workflow editor. Select **Review record**. For a single-owner local test, explicitly enable **Allow the run requester to approve, if they are an owner or admin**; otherwise use a different owner/admin reviewer.
- [ ] Save/validate the workflow and paste its sample into **Input JSON**. Confirm **Preview** is disabled because approval/timer steps need a published durable run. Choose **Publish**, then **Run**, then **Open durable step debugger**. Inspect the saved approval input and choose **Approve and continue** as the permitted reviewer. Confirm the five-second timer and final completion/output in workflow executions. If you choose **Reject run** instead, record that result rather than expecting the approval path. Agent/model/external-service steps likewise require published runs and their referenced connections/published agents.

## Record the user's result

Record date, recipe, safe draft/run IDs, browser, completed boxes and safe errors. Do not record keys or private customer data. This checklist has source verification only until the user completes it; automated tests do not replace real-provider acceptance or the signed-in GUI walkthrough.

## Source map

All route directories below are under `frontend/src/app/w/[workspaceId]/`:

| Path | Source for controls/behavior |
|---|---|
| `start/page.tsx`, `templates/page.tsx` | `features/workspace/task-start.tsx`, `task-start-model.ts`; `features/templates/template-gallery.tsx` |
| `agents/skills/page.tsx`, `agents/skills/[skillId]/page.tsx` | `features/agents/skill-library.tsx`, `skill-editor.tsx` |
| `integrations/page.tsx` | `features/workspace/provider-connection.tsx` |
| `agents/[agentId]/page.tsx` | `features/agents/agent-editor.tsx`, `builder-blocks.tsx`, `try-panel.tsx` |
| `workflows/[workflowId]/edit/page.tsx` | `features/workflows/workflow-builder.tsx`, `node-config.ts`, `node-config-forms.tsx` |
| `executions/page.tsx`, `executions/[runId]/page.tsx` | `features/executions/workflow-console.tsx` and execution detail components |

Recipe/sample definitions: `backend/app/modules/templates/{catalog,approval_starter}.py`; skill definitions: `backend/app/modules/skills/catalog.py`. Source checks confirm paths and controls exist; no GUI outcome is asserted here.
