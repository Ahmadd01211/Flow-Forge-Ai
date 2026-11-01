# Workspace MCP servers and tool policies

Until this slice, MCP servers could only come from the operator's `MCP_CATALOG_JSON`, which is empty by default, and agents could only call tools the operator had listed as read-only. In practice agents could not reach any external system. This slice lets workspace owners and admins add their own servers and decide, tool by tool, what agents and workflows may call. It also fixes two client bugs that had prevented every real MCP connection from working.

## Try it locally

1. Open **Integrations → MCP servers → Add server**. Enter a name and the server's Streamable HTTP URL, plus a bearer token if the service needs one. For a no-auth test, `https://mcp.deepwiki.com/mcp` works.
2. FlowForge connects, lists the server's tools and shows each one as **Read-only**, **Write** or **Destructive**, based on the labels the server publishes.
3. Choose **Allow** or **Block** for each tool. Read-only tools start allowed; everything else starts blocked.
4. In the agent editor, grant allowed tools to an agent and publish. In the workflow builder, use an **MCP tool** step. To have a person review each action, put a **Human approval** step before it.
5. Owners and admins can test any allowed tool from the server panel. Editors can test only read-only tools; write tools otherwise run from agents or published workflows.

## Policy rules

| Tool | Default | Who can change it |
|---|---|---|
| Operator server, listed in `read_only_tools` | Allow | Admins can block it |
| Operator server, any other listed tool | Block | Admins can allow it, unless the install is locked down |
| Workspace server, marked read-only and not destructive | Allow | Admins |
| Workspace server, unmarked, write or destructive | Block | Admins |

A tool's labels are claims made by the remote server, not guarantees. That is why the defaults only trust a read-only label to *allow* a tool, never to widen permissions further, and why every write needs an explicit admin decision. Policy is checked whenever a tool is about to run: at agent publication, at run submission and immediately before each remote call. Blocking a tool therefore stops queued and running work before its next call, without republishing. Allowing a tool does not grant it to anything; agents and workflows still pin specific tools in their published versions.

Every decision is in the activity log as `mcp.server_added`, `mcp.connected`, `mcp.tool_policy_changed` (including whether the tool was read-only) or `mcp.revoked`.

## Endpoints, secrets and network safety

- Only public HTTPS hosts on port 443 are accepted. IP literals, `localhost`, `.local` and `.internal` names, and URLs containing user credentials are rejected. DNS is re-checked before every connection, and addresses that resolve to private networks are blocked. Production still needs an egress policy, because a DNS answer can change between the check and the connection.
- Some services, such as Zapier, embed a key in the URL path. The full URL is therefore encrypted together with the token using the workspace credential key. The database, listings and audit events keep only the `https://host` origin.
- Rotating a token re-lists the tools and keeps policies for tools that still exist. Removing a server deletes its stored URL and token; agents and workflows that use it stop before their next call. To use it again, add it again.
- Tools whose names or input schemas FlowForge does not support are skipped, and the add result says how many were skipped. The schema subset excludes `anyOf`, `$ref` and `pattern`, so some real tools (for example DeepWiki's `ask_wiki_question`) are skipped for now.
- A workspace can add up to 20 servers.

## Locked-down installs

Operators who want the previous behavior can set:

```json
{"servers": [ ...reviewed catalog entries... ], "workspace_servers": false}
```

Workspace-added servers then disappear from listings and stop working. Admins can still block operator tools but cannot allow tools the operator did not mark read-only. The original list format remains valid and means workspace servers are allowed.

## Bugs fixed along the way

The MCP Python SDK 2.x exposes snake_case attributes (`input_schema`, `read_only_hint`) and dumps results in snake_case unless asked for wire-format aliases. The client read `tool.inputSchema`, which raised and was reported as `MCP_CONNECT_FAILED` for every real server. It also checked `isError` on a snake_case dump, so failed tool calls looked successful. Both are fixed. A regression test uses real SDK types, and the client was verified against DeepWiki's live server. Earlier tests had replaced `discover()`, which is why these bugs went unnoticed.

## Decisions and alternatives

Allow/Block is enforced where it cannot be bypassed: one registry module resolves servers and policies for agent publication, workflow validation, both runtimes and direct tests. Approval *inside* an agent's tool loop needs agent runs that can pause and resume with an encrypted transcript, so it is the next slice. Until then, a Human approval step in a workflow provides review for workflow-driven writes. OAuth sign-in for MCP (the SDK ships `OAuthClientProvider`) follows once it can be tested against real accounts. stdio servers are not supported, because running arbitrary local processes needs a sandbox.

## Tests

`tests/test_mcp_workspace_servers.py` covers secret-URL handling, URL and role checks, default and explicit policies, direct tests by role, an agent calling an allowed write tool, blocking a run that was already queued and refusing new runs, workflow validation, locked-down mode, rotation and removal, and real SDK types. The existing MCP suites pass unchanged. Migration `0025` was downgraded and re-applied on the test database. A live check against the deployed stack added DeepWiki, allowed a tool, ran a published workflow through the Celery worker with real output, blocked the tool and confirmed that new runs were refused.
