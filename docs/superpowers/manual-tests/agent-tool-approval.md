# Manual GUI Check: Agent Tool Approval

This feature pauses only write-capable MCP calls. For a GUI run, use a **sandbox MCP server** with a harmless test action and a workspace with a second owner/admin who can review the requester’s call.

## GUI walkthrough

1. Start the local app with `docker compose up -d --build` and open `http://localhost:8080`.
2. Sign in as a workspace owner/admin. Connect a provider account and publish an agent that has one write-capable MCP tool granted. Configure its MCP policy as **Allow**.
3. Use a sandbox tool whose action is safe to repeat in that sandbox, such as creating a disposable test record. Make the agent request that tool for the test input.
4. Open **Runs**, then select **Open full trace**. Confirm the run says **waiting**, the panel shows the server, tool, write warning, exact arguments, requester and expiry, and the requester has no decision buttons.
5. Sign in as a different workspace owner/admin and reopen the same trace. Confirm **Approve and continue** and **Reject call** are visible.
6. Approve. Confirm the trace reports that the run is queued, then refresh until it completes. Confirm the sandbox recorded exactly one tool call and the model response includes that call’s result.
7. Start another test run and reject the pending call. Confirm the run ends and the sandbox records no action.
8. Start another test run and cancel it from Runs while it is waiting. Confirm the run is cancelled and the trace no longer offers a decision.
9. If the run is deployment-originated, verify the trace identifies both the deployment name and its creator as requester.

## No-cost automated path

To exercise the approval lifecycle without a paid model request or a live write-capable MCP account, run from the repository root:

```powershell
docker compose run --build --rm tests pytest -p no:cacheprovider tests/test_agent_tool_approvals.py -q
```

The test suite stubs the provider response and MCP transport, and verifies approval, rejection, cancellation, expiry, policy drift, deployment identity, single-call resume and uncertain-outcome handling. The GUI walkthrough still needs a sandbox MCP server and a configured provider to generate a real run.

## Expected safety checks

- A requester cannot approve their own run, including a deployment run.
- A viewer/editor cannot approve; an owner/admin other than the requester can.
- Read-only tools continue without a pause.
- A changed MCP connection, schema, policy or read/write classification prevents the old approval from executing.
- If a write call’s outcome is uncertain, the agent run reports that uncertainty and does not automatically call the MCP tool again.
