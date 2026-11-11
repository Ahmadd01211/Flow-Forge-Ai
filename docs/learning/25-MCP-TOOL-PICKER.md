# Find MCP tools in workflow steps

Use this checklist to review the searchable MCP picker in the workflow editor.

1. Start the local stack with `docker compose up -d --build`, then open [http://localhost:8080](http://localhost:8080) and sign in.
2. Open **Workflows**, edit a workflow, and add or select an **MCP tool** step.
3. Type `wiki`, `GitHub`, or a word from a tool description into **Approved MCP tool**. Results should filter across server name, tool name, and description, and remain grouped under their server.
4. Check that results show the tool description when available and a **Read only** or **Can write** label. The label describes the connected tool policy; it does not change that policy.
5. Select a tool and confirm the selection and its input schema appear. Clear the selection and choose another tool; the workflow retains the selected server/tool identity.
6. Search for a phrase with no matches and confirm a no-results message. If no tools are allowed, the form should link to **Integrations**.
7. Use the keyboard: focus the search field, type a query, use Up/Down to move through results, Enter to select, Escape to close the result list, and **Clear selection** to remove the current tool.

This picker lists runnable, allowed tools only. Approval, execution safety, and publication checks remain enforced by the existing MCP policy and workflow runtime. Selecting a write-capable tool can change data in the connected service when the published workflow runs; review the tool and its inputs before publishing.
