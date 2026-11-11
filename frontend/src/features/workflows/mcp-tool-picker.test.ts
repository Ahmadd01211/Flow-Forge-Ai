import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import { McpToolPicker } from "./mcp-tool-picker";

const options = [
  {
    id: "deepwiki-1",
    name: "DeepWiki",
    runnable_tools: ["ask_wiki_question"],
    runnable_schemas: { ask_wiki_question: { type: "object" } },
    tools: [
      {
        name: "ask_wiki_question",
        description: "Search repository documentation",
        read_only: true,
      },
    ],
  },
  {
    id: "github-2",
    name: "GitHub",
    runnable_tools: ["create_issue"],
    runnable_schemas: { create_issue: { type: "object" } },
    tools: [{ name: "create_issue", description: "Create an issue", read_only: false }],
  },
];

describe("MCP workflow picker", () => {
  it("renders grouped accessible options with descriptions, permissions, and current selection", () => {
    const html = renderToStaticMarkup(
      createElement(McpToolPicker, {
        workspaceId: "workspace-1",
        servers: options,
        value: { server_id: "deepwiki-1", tool_name: "ask_wiki_question" },
        onChange: vi.fn(),
      }),
    );

    expect(html).toContain('role="combobox"');
    expect(html).toContain('role="listbox"');
    expect(html).toContain('role="option"');
    expect(html).toContain("DeepWiki");
    expect(html).toContain("GitHub");
    expect(html).toContain("Search repository documentation");
    expect(html).toContain("Read only");
    expect(html).toContain("Can write");
    expect(html).not.toContain("aria-activedescendant=");
    expect(html).toContain("ask_wiki_question");
  });

  it("shows a useful no-match state and keeps the Integrations recovery link when empty", () => {
    const noTools = renderToStaticMarkup(
      createElement(McpToolPicker, {
        workspaceId: "workspace-1",
        servers: [],
        value: { server_id: "", tool_name: "" },
        onChange: vi.fn(),
      }),
    );
    expect(noTools).toContain("No approved MCP tools are available");
    expect(noTools).toContain("/w/workspace-1/integrations");
  });
});
