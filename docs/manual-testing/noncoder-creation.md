# Noncoder creation: manual GUI checklist

Updated from source on 12 November 2026. **Not yet executed in the GUI: final walkthrough belongs to the user.** Tick boxes only after observing the result. Use the running local app at `http://localhost:8080`. Replace `<workspaceId>`, `<agentId>` and `<workflowId>` below with the IDs in its URLs. Use an owner/admin account for provider setup and an editor or above for draft creation. Use safe sample data: drafts and copied skills are workspace-visible.

## Register and open a workspace

- [ ] From the public page choose **Start building** (or open `/register`). Fill **Your name**, **Workspace name**, **Email address**, and a unique **Password** of at least 12 characters, then **Create workspace**. Confirm the workspace overview at `/w/<workspaceId>/overview`. Existing users can use `/login`; `/app` opens the first workspace or `/workspaces` when none exists.
- [ ] Open `/w/<workspaceId>/settings`. If email is unverified, choose **Send verification email**. In local development open Mailpit at `http://localhost:8025`, follow your verification link to `/verify-email#<token>` and choose **Continue**, then **Open your workspace**. Return to Settings and confirm **Email verified**. Do not record the token.
- [ ] If creating another workspace, open `/workspaces`, fill **New workspace name**, and **Create workspace**. Use that workspace's ID in the paths below. Open `/w/<workspaceId>/start` to begin.

## Discover, preview and create

- [ ] Open `/w/<workspaceId>/start`. Confirm **Try without a model**, **Preview duplicate removal**, **Choose what to build**, **Browse task recipes**, **Preview support triage**, **Create a blank agent**, and **Open workflows**. Choose **Browse task recipes**, reaching `/w/<workspaceId>/templates`.
- [ ] In **Search recipes**, enter `I want to draft a customer reply`. Confirm **Customer reply draft** matches and has **Recommended**. Set **Category** to **Support** and confirm the match remains. Clear search, select **Productivity**, and confirm **Meeting action items** is recommended. Search `zzzznomatch` and confirm the no-results message; restore **All categories** and clear search.
- [ ] Click **Preview** on **Customer reply draft**. Read **Expected result**, **Required setup**, **Skills copied as editable drafts**, **Sample input**, and expand **Recipe instructions and steps**. Confirm the copy explains workspace visibility, review/publication, and possible provider charges. Browsing and previewing must not create an agent or submit a model run.
- [ ] Choose **Close preview**; keyboard focus should return to its Preview button. Preview it again, then choose **Create workspace draft**. Confirm **Workspace draft created: Customer reply draft**, the unpublished/unrun status, links for both attached skills, and **Continue setup**. Creation should leave you at this handoff, without automatically testing or publishing. **Continue setup** carries `?recipe=<key>` on the existing editor route; confirm the supplied sample initializes the test form and the expected example appears. Imported recipes with no sample ask you to enter safe input; missing/unavailable recipe metadata must still open the normal editor. No second draft should be created.

## Review skills, connect a provider and test an agent

- [ ] Open each **Review attached skill** link (retain the handoff or its agent-editor link in another tab). Each opens `/w/<workspaceId>/agents/skills/<skillId>`. Review **When should an agent use it?**, **Instructions**, **Examples**, and **Tools this skill needs**. Customize Brand voice to your actual guidance, especially example promises/policies. Use **Save** for edits and **Publish** for each skill. Confirm **Published**, a version number and a Versions entry. `/w/<workspaceId>/agents/skills` should list both copies.
- [ ] Open `/w/<workspaceId>/integrations`. Even with no active provider, confirm **Connect a model provider**, **Choose provider**, and **Verify API key** are available. Choose your provider in **Model provider**, enter your own credential in its API key field, and choose **Verify key**. Keep the key in this interface; never put it in the checklist or chat.
- [ ] On successful verification, confirm the key-verified notice and **Choose a model**. Use **Search available models**, select a runnable model, review capability/pricing information and choose **Save default model**. **Show models for setup only** exposes unsupported listings; those are not generation acceptance. Use **Refresh models** without re-entering the saved key and confirm the list refreshes. Switching providers must show that provider's own connection/model state.
- [ ] For a previously unconnected provider, a verification/listing failure must show an error without claiming the provider is connected. A failed saved-key refresh should preserve the prior catalog/default and connection. Record only the provider name and safe error text. Resolve access/billing/model availability with your own account before the real test. Verification/catalog refresh alone does not confirm generation access or billing capacity.
- [ ] Return via **Continue setup** to `/w/<workspaceId>/agents/<agentId>` (reload after provider/skill changes). Open **Brain**, choose the connected provider and a model marked **Live runs**. Open **Skills** and confirm both copied skills remain attached and display published versions. Review instructions, input/output fields and run budget; choose **Save** if changed.
- [ ] In **Try your agent**, fill `customer_message` with `Hello, could you let me know the shipping status of my order?` and `brand_guidelines` with `Use a clear, warm tone. Ask for an order number when details are missing.` Choose **Run it**. This submits a real budgeted provider run and can incur charges. Check that the output has `draft_reply` and `needs_human`, requests missing information and invents no shipping status. This recipe drafts text; it sends no customer message.
- [ ] Open **Trace** on the result to `/w/<workspaceId>/executions/<runId>`; inspect recorded outcome/usage. A failed run is not accepted generation. Record safe error details if needed. In the editor choose **Publish**, resolve readiness issues, then **Publish version**. Confirm the agent's Published version status. Publication and testing are separate actions.
- [ ] If a skill is edited again, **Save** and **Publish** a new skill version; reload the agent, review readiness and republish the agent to update its pinned skill version. Existing published agent versions retain their pins.

## Sample evidence and rechecks

- [ ] In either editor, observe the compact launch checklist. A fresh session starts at **Not tested in this session**; existing execution history is still available. Run a sample explicitly, inspect its output, and record acceptance in this guide only after reviewing the result. A successful request alone does not confirm the output is useful.
- [ ] Edit agent settings/skills, workflow graph or sample input after testing. Confirm the checklist asks for a fresh test/review for the changed configuration/input. Reload: session evidence resets; no localStorage progress or historical run becomes a fresh sample pass. Testing remains optional for publication, and publishing never runs anything.

## Local workflow preview and durable run

- [ ] Return to Task recipes. Search `text cleanup`, **Preview** **Text cleanup**, **Create workspace draft**, then **Continue setup**, reaching `/w/<workspaceId>/workflows/<workflowId>/edit`.
- [ ] Choose **Validate** (or **Save & validate** after edits). In **Draft preview** set **Input JSON** to `{"text":"Hello world","find":"world","replacement":"team"}` and choose **Preview**. Confirm **Output JSON** is `{"text":"Hello team"}` and step statuses appear. This uses a local approved tool, needs no provider and creates no durable full-run record.
- [ ] Choose **Publish** after successful validation; confirm **Published version ready**. With the same Input JSON, choose **Run**. Confirm a durable run ID/state and follow **Open durable step debugger** to `/w/<workspaceId>/executions?kind=workflows&runId=<runId>`. Inspect persisted step evidence/output. A publish by itself must not submit a run; unsaved edits disable Run until saved/published again.
- [ ] Also preview/create **Route requests by category**. In its workflow editor select **Route by category** and review the Switch cases and Default route. Validate, then locally preview `{"category":"billing"}`: expect `{"queue":"billing-team"}`. Repeat with `technical` for `technical-support` and `other` for `general-support`; only the selected route runs. Publish and Run one input, then inspect the selected branch and skipped alternatives in the durable debugger.
- [ ] From **Try without a model** at Start, choose **Preview duplicate removal**. Preview/create **Remove duplicate contacts**, then **Continue setup**. Confirm its source sample initializes **Input JSON** and its expected example appears. Select **Remove duplicates** in the editor and review `/items` as the source and `/email` as the comparison field. Validate and locally Preview: expect Ada's first record followed by Lin, `count: 2`, and `removed: 1`. Comparison is exact and case-sensitive; it keeps the first matching record in source order. Publish and Run the same input and confirm the persisted output matches. Both recipes work without a provider or external connection. This claim applies to these known local recipes; other workflows can require setup.
- [ ] For a publication-required example, preview **Review and release** in Task recipes and copy its **Sample input**. Create its workspace draft and open the workflow editor. Select **Review record**. For a single-owner local test, explicitly enable **Allow the run requester to approve, if they are an owner or admin**; otherwise use a different owner/admin reviewer.
- [ ] Save/validate the workflow and paste its sample into **Input JSON**. Confirm **Preview** is disabled because approval/timer steps need a published durable run. Choose **Publish**, then **Run**, then **Open durable step debugger**. Inspect the saved approval input and choose **Approve and continue** as the permitted reviewer. Confirm the five-second timer and final completion/output in workflow executions. If you choose **Reject run** instead, record that result rather than expecting the approval path. Agent/model/external-service steps likewise require published runs and their referenced connections/published agents.

## External workflow setup and explicit run

- [ ] Preview **AI priority routing with action**. Follow its setup order: create **Support ticket triage**, review/publish copied skills if present, select a connected live model, test explicitly, then publish the agent. In the workflow select that published agent version in **Classify ticket**. An owner/admin must separately approve the intended API tool and JSON contract, then select it in **Escalate urgent**. Review budgets and the external destination before publishing.
- [ ] Validate/save the workflow. Its model/API steps disable local draft preview. **Publish** creates an immutable version and must not execute anything. Only choose **Run** when you explicitly intend a real provider call and possible external write/charge. Test urgent and normal inputs against your intended safe destination; inspect durable execution evidence, confirming only the urgent path sends the action. Enable triggers only after reviewing those outcomes. If using MCP, review tool permissions and required action approvals separately; these are not proven by local examples.

## Final GUI acceptance

- [ ] Registration/login, email verification and workspace start completed in the selected browser.
- [ ] Recipe search, category filtering, keyboard preview focus and workspace-draft handoff observed.
- [ ] Attached skills reviewed/published before agent testing; the user's own provider key verified and model selected.
- [ ] A real agent test completed with reviewed output and trace; agent publication completed separately.
- [ ] Local workflow preview and a separately published durable run completed with matching expected output, including Switch/default routing and duplicate removal.
- [ ] Approval/rejection and timer behavior observed with the intended reviewer permissions.
- [ ] External workflow setup/publication order and explicitly authorized provider/API (or MCP) runs observed.

## Record the user's result

Record date, recipe, safe draft/run IDs, browser, completed boxes and safe errors. Do not record keys or private customer data. Automated Task 4 checks: six focused frontend suites (60 tests), TypeScript, and scoped lint; integrated checks are recorded separately by the controller. Signed-in GUI, live provider, API/MCP external-action acceptance have not been performed in this slice. Automated tests do not replace them.

## Source map

Account routes are `frontend/src/app/{register,login,verify-email,app,workspaces}/page.tsx`; their forms are `features/auth/{auth-form,account-action}.tsx` and `features/workspace/workspace-start.tsx`. Email verification is offered by `features/workspace/settings-panel.tsx`.

All workspace route directories below are under `frontend/src/app/w/[workspaceId]/`:

| Path | Source for controls/behavior |
|---|---|
| `start/page.tsx`, `templates/page.tsx` | `features/workspace/task-start.tsx`, `task-start-model.ts`; `features/templates/template-gallery.tsx` |
| `agents/skills/page.tsx`, `agents/skills/[skillId]/page.tsx` | `features/agents/skill-library.tsx`, `skill-editor.tsx` |
| `integrations/page.tsx` | `features/workspace/provider-connection.tsx` |
| `agents/[agentId]/page.tsx` | `features/agents/agent-editor.tsx`, `builder-blocks.tsx`, `try-panel.tsx` |
| `workflows/[workflowId]/edit/page.tsx` | `features/workflows/workflow-builder.tsx`, `node-config.ts`, `node-config-forms.tsx` |
| `executions/page.tsx`, `executions/[runId]/page.tsx` | `features/executions/workflow-console.tsx` and execution detail components |

Recipe/sample definitions: `backend/app/modules/templates/{catalog,approval_starter,practical_starters}.py`; skill definitions: `backend/app/modules/skills/catalog.py`. Source checks confirm paths and controls exist; no GUI outcome is asserted here.
