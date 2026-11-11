# Searchable MCP Tool Picker Design

## Intent

Make choosing an already-approved MCP tool in a workflow step easier when a workspace has many tools. Users should find a tool by name or description and understand its server and read/write status before selecting it.

## Goals

- Replace the long flat native select in the workflow MCP step editor with a keyboard-accessible searchable picker grouped by server.
- Show each tool's name, concise description when available, and read-only/write status from existing MCP metadata.
- Preserve the current workflow config shape (`server_id` and `tool_name`), selected schema preview, policy enforcement, and publish/runtime behavior.
- Keep the path to Integrations available when there are no runnable allowed tools.

## Non-goals and anti-goals

- Do not change MCP connection, Allow/Block policy, permission roles, API contracts, or runtime behavior.
- Do not show blocked/unapproved tools as selectable options or infer safety from descriptions.
- Do not redesign the Integrations approval flow or agent tool-grant UI in this slice.
- Do not add a picker dependency; use existing React, TypeScript, and project UI patterns.

## Approaches considered

1. Keep the native select and only sort or relabel options. This is the smallest change, but it remains difficult to search or compare tools.
2. Add a searchable, server-grouped picker inside the existing MCP workflow form. It reuses currently supplied names, schemas, and read-only flags, improves discovery, and leaves stored workflow configuration unchanged. **Recommended and selected.**
3. Build a shared MCP catalog browser across workflow authoring and Integrations. This could unify discovery and approval but expands the change into separate permission and connection workflows.

## Design

The MCP workflow form will render a focused search input and grouped result list. Search matches the server name, tool name, and available description without changing the server/tool identity used in configuration. Results show a plain read-only or write label and any available description. Selecting a result writes the same `{ server_id, tool_name }` pair as today; the existing schema preview and pinning hint remain. Empty search results get a clear message, while an empty runnable-tool list retains the existing Integrations link. Keyboard users can search, navigate results, choose one, and clear the selection.

The backend and permission boundary remain authoritative. Only tools already present in `runnable_tools` are offered, and descriptions/read-only labels are informational metadata rather than new authorization rules.

## Constraints and verification

- Keep the existing Next.js/React/TypeScript stack and avoid new dependencies.
- Test normalization/filtering and selection mapping as pure helpers; test rendered labels and keyboard-accessible controls at the component seam.
- Run focused Vitest tests, ESLint, TypeScript typecheck, API drift check, production build, and the full backend suite to confirm no contract/runtime change.
- Leave final interactive GUI confirmation to the user and provide a short manual checklist.

## Builder decisions

- Component placement and keyboard interaction details remain implementation choices, following the existing workflow form and accessible UI conventions.
- If tool descriptions are missing or blank, show the name and read/write label without placeholder prose.
