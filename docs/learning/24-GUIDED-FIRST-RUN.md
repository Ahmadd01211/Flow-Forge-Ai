# Guided first run: support ticket triage

This walkthrough starts with the built-in support ticket triage agent, tests it with a real provider, and leaves it published for later use. A provider key is required for a real model call; the call may incur charges. A provider connection alone does not select a model in the agent, so complete both setup steps.

## Start the app

1. Start Docker Desktop, then run `docker compose up -d --build` from the repository root. Open [http://localhost:8080](http://localhost:8080), sign up, verify the local development email at [http://localhost:8025](http://localhost:8025) if prompted, and open your workspace. There is no shared demo login.
2. From the workspace Overview, select **Choose a task**, then choose **Support ticket triage**. The Templates page should put this starter first and mark it **Recommended**.
3. Select **Preview** on the template card. Confirm the instructions, setup steps, and sample input are shown. Select **Use template** to create a private editable agent draft.

If the app is unavailable, check `docker compose ps` and service logs with `docker compose logs --tail=100 api frontend`. If the recommended link is missing, open **Templates** directly and choose **Support ticket triage**.

## Connect, configure, and test

4. In the agent editor, open **Input & output** and keep the `ticket` input and `priority`/`reason` output contract. Open **Model** and choose a supported model. If no provider is connected, select **Integrations** in the workspace navigation to save your own provider key, then return to the editor and select the model. Provider keys are encrypted by the app; never paste them into agent instructions. Saving a provider key is restricted to a workspace owner/admin.
5. Select **Save** so the draft has an agent ID. In **Try your agent**, submit this JSON input and select **Run it**:

   ```json
   {"ticket":"Our payment service is down and customers cannot check out."}
   ```

   The panel runs current settings, including unsaved edits after an agent exists. A successful live run returns `priority` and a short, ticket-grounded `reason`. The test uses the selected provider and can incur charges. A setup-only model, missing key, invalid schema, or exhausted workspace budget will prevent a live run; use the readiness message, choose a runnable model, fix the key/schema, or check **Usage & budgets**.

6. Select **Save**, then **Publish**. Resolve any readiness issues using their **Fix it** links. When checks pass, select **Publish version**. The separate **Test snapshot** action checks a frozen contract and does not call a provider; it is not evidence of a live model run.
7. In the editor's **Use it** section, open the agent chat to run the published version. Then open **Executions** and select that run to inspect its trace, input, output, and provider usage. Failed runs remain visible there with their error code.

For a no-provider-cost starter, go back to **Templates** and preview **Review and release**. Its workflow uses local field mappings and a timer; its setup steps include sample input and the approval path. Trigger configuration is optional for this walkthrough: publishing and manually running does not create a webhook or schedule. Configure **Triggers & schedules** only when you intentionally want automatic starts.

## Try the blank starting points

From Overview, choose **Choose a task** again:

- **Blank agent** opens the new agent editor. Name it, add instructions, set its input/output schemas, choose a model, save, and publish.
- **Blank workflow** opens the workflow library. Select **Create workflow**, then add and connect nodes in the existing workflow builder. Manual input, approved local tools, and result steps are runnable; agent and branch nodes remain editable drafts while their runtime is completed.

Both destinations stay inside the current workspace. A blank workflow can use local nodes without a provider; any model or external service steps require their own setup and may incur charges.

## GUI handoff checklist

- [ ] Overview's **Choose a task** opens all three starting choices.
- [ ] Support triage is first and marked **Recommended**; its preview includes setup steps and sample JSON.
- [ ] **Use template** creates an editable draft and opens the agent editor.
- [ ] A real provider-backed test returns the expected output fields (or the editor clearly explains the setup/readiness error).
- [ ] Save and publish produce a published version; **Use it** opens chat.
- [ ] The run appears under **Executions** and its trace is inspectable.
- [ ] Blank agent and blank workflow choices stay in the selected workspace.
- [ ] No webhook or schedule appears unless you explicitly create one.
