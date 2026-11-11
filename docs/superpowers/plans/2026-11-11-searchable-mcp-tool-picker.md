# Searchable MCP Tool Picker Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make allowed MCP tools in workflow steps easy to find and understand without changing workflow configuration or permission behavior.

**Architecture:** Add a pure model for flattening/grouping and searching the existing workspace MCP options, then render it through a small accessible client component used by the current MCP node form. Pass through the tool description and effective read-only status already returned by the MCP endpoint; continue writing only the existing `server_id` and `tool_name` fields.

**Tech Stack:** Next.js App Router, React, TypeScript, Vitest, existing MCP listing API.

**Spec:** `docs/superpowers/specs/2026-11-11-searchable-mcp-tool-picker-design.md`

## Global Constraints

- Do not change MCP connection, Allow/Block policy, permission roles, API contracts, or runtime behavior.
- Do not show blocked/unapproved tools as selectable options or infer safety from descriptions.
- Do not redesign the Integrations approval flow or agent tool-grant UI in this slice.
- Do not add a picker dependency; use existing React, TypeScript, and project UI patterns.
- Keep the current saved workflow config shape: `{ server_id, tool_name }`.

## Review Focus

- Search is case-insensitive and matches server name, tool name, and description; test each field and empty query.
- Missing or blank descriptions do not hide a tool or render placeholder copy; test absent metadata.
- Selected values remain stable when search filters or groups reorder; test selection mapping uses the original server ID and tool name.
- Only `runnable_tools` are rendered; test blocked tools present only in other metadata are absent.
- No allowed tools and no search matches show distinct helpful states; test both and preserve the Integrations link in the no-tools case.

---

### Task 1: Model searchable MCP options

**Files:**
- Create: `frontend/src/features/workflows/mcp-tool-picker-model.ts`
- Create: `frontend/src/features/workflows/mcp-tool-picker-model.test.ts`
- Modify: `frontend/src/features/agents/model-tools.tsx` (shared `McpServerOption` metadata type)

**Interfaces:**
- Consumes: `McpServerOption[]` with `id`, `name`, `runnable_tools`, `runnable_schemas`, and optional tool metadata `{ name, description?, read_only }`.
- Produces: `mcpToolOptions(servers)` returning options with `serverId`, `serverName`, `toolName`, optional `description`, `readOnly`, and the original input schema; `filterMcpToolOptions(options, query)` returning matching options in stable server/tool order; `nextMcpToolIndex(current, key, count)` wrapping arrow-key navigation through the visible options; and `mcpToolConfig(option)` returning the persisted `{ server_id, tool_name }` pair.

- [x] **Step 1: Write failing model tests**

Test flattening multiple servers, matching by server/tool/description case-insensitively, retaining all options for an empty query, handling missing descriptions, and excluding tools not listed in `runnable_tools`. Test that ArrowDown/ArrowUp navigation wraps through visible options and that selection mapping preserves the exact server ID and tool name.

- [x] **Step 2: Run the focused model tests and confirm the missing-module failure**

Run from `frontend`: `npm run test -- src/features/workflows/mcp-tool-picker-model.test.ts`.

- [x] **Step 3: Implement the minimal typed model and extend the option metadata type**

- [x] **Step 4: Re-run the focused tests and verify they pass**

- [x] **Step 5: Commit the task**

### Task 2: Add the accessible workflow picker

**Files:**
- Create: `frontend/src/features/workflows/mcp-tool-picker.tsx`
- Create: `frontend/src/features/workflows/mcp-tool-picker.test.ts`
- Modify: `frontend/src/features/workflows/node-config-forms.tsx`
- Modify: `frontend/src/app/w/[workspaceId]/workflows/[workflowId]/edit/page.tsx`

**Interfaces:**
- Consumes: `mcpToolOptions` and `filterMcpToolOptions` from Task 1, plus the existing `FormContext.mcpOptions` data.
- Produces: a picker that emits the selected `{ server_id, tool_name }`, renders server-grouped accessible options with read-only/write labels and optional descriptions, and retains a link to Integrations when no runnable options exist.

- [x] **Step 1: Write failing rendered-component tests**

Render the picker with multiple servers and assert group headings, tool descriptions, read-only/write labels, selected value, filtering, no-match feedback, and the no-tools Integrations link. Keep interaction details in pure helpers covered in Task 1 because the current Vitest setup has no DOM test environment; test arrow-key index movement and exact `{ server_id, tool_name }` mapping there, then verify the component exposes combobox/listbox/option semantics in rendered markup.

- [x] **Step 2: Run focused component tests and verify the picker is missing**

- [x] **Step 3: Implement the keyboard-accessible searchable grouped picker**

Use semantic search input/listbox/option roles or an equivalent accessible pattern with arrow-key navigation, Enter selection, Escape dismissal, an explicit Clear button, and a visible selection. Keep read/write labels informational only.

- [x] **Step 4: Pass endpoint descriptions and read-only flags through the edit page and replace the current select**

Preserve the schema preview, publication-pinning hint, field issues, and selected workflow config shape.

- [x] **Step 5: Run focused tests, ESLint, and TypeScript typecheck**

- [x] **Step 6: Commit the task**

Implementation note: Vitest has no DOM environment, so keyboard wraparound and config mapping are tested as pure model helpers, while the actual component is checked through React server-rendered semantic markup. ESLint caught and required focus/keyboard semantics on role=option elements; the input remains the active-descendant controller and options also support direct keyboard activation.

### Task 3: Full verification and manual handoff

**Files:**
- Modify: `docs/PROJECT_STATUS.md`
- Create: `docs/learning/25-MCP-TOOL-PICKER.md`
- Modify: `README.md`

**Interfaces:**
- Consumes: the completed MCP workflow picker and current local Compose stack.
- Produces: fresh verification evidence and a short user-run GUI checklist.

- [x] **Step 1: Run frontend Vitest, ESLint, TypeScript typecheck, API drift check, and production build**
- [x] **Step 2: Run backend PostgreSQL/Redis suite and Ruff**
- [x] **Step 3: Confirm local readiness and migration head**
- [x] **Step 4: Record fresh evidence and document manual GUI steps**
- [x] **Step 5: Commit the task, review the branch, and push the current feature branch**

Implementation note: Enter at initial focus does not select a tool until the user searches or navigates. Final review found that keyboard navigation could highlight off-screen results and an empty query result could leave a stale active descendant; both were fixed with RED/GREEN model/component tests, and active options now scroll into view. Final frontend tests, lint, typecheck, API drift, and production build passed.

## Task graph

`1 -> 2 -> 3`
