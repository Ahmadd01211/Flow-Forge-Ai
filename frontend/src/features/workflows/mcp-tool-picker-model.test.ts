import { describe, expect, it } from "vitest";
import {
  filterMcpToolOptions,
  mcpToolConfig,
  mcpToolOptions,
  nextMcpToolIndex,
} from "./mcp-tool-picker-model";

const servers = [
  {
    id: "deepwiki-1",
    name: "DeepWiki",
    runnable_tools: ["ask_wiki_question", "read_wiki_contents"],
    runnable_schemas: {
      ask_wiki_question: { type: "object", description: "Ask about a repository" },
      read_wiki_contents: { type: "object" },
      blocked_tool: { type: "object" },
    },
    tools: [
      { name: "ask_wiki_question", description: "Search repository documentation", read_only: true },
      { name: "read_wiki_contents", read_only: true },
      { name: "blocked_tool", description: "Must not appear", read_only: false },
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

describe("MCP workflow picker model", () => {
  it("flattens only runnable tools and retains server identity, descriptions, status, and schema", () => {
    expect(mcpToolOptions(servers)).toEqual([
      {
        serverId: "deepwiki-1",
        serverName: "DeepWiki",
        toolName: "ask_wiki_question",
        description: "Search repository documentation",
        readOnly: true,
        schema: { type: "object", description: "Ask about a repository" },
      },
      {
        serverId: "deepwiki-1",
        serverName: "DeepWiki",
        toolName: "read_wiki_contents",
        description: undefined,
        readOnly: true,
        schema: { type: "object" },
      },
      {
        serverId: "github-2",
        serverName: "GitHub",
        toolName: "create_issue",
        description: "Create an issue",
        readOnly: false,
        schema: { type: "object" },
      },
    ]);
  });

  it("filters case-insensitively by server, tool name, and description while preserving order", () => {
    const options = mcpToolOptions(servers);
    expect(filterMcpToolOptions(options, "GITHUB").map((item) => item.toolName)).toEqual([
      "create_issue",
    ]);
    expect(filterMcpToolOptions(options, "WIKI_CONTENTS").map((item) => item.toolName)).toEqual([
      "read_wiki_contents",
    ]);
    expect(filterMcpToolOptions(options, "repository documentation").map((item) => item.toolName)).toEqual([
      "ask_wiki_question",
    ]);
    expect(filterMcpToolOptions(options, " ")).toEqual(options);
  });

  it("wraps active option movement and maps selection to the saved config fields", () => {
    const options = mcpToolOptions(servers);
    expect(nextMcpToolIndex(-1, "ArrowDown", options.length)).toBe(0);
    expect(nextMcpToolIndex(2, "ArrowDown", options.length)).toBe(0);
    expect(nextMcpToolIndex(0, "ArrowUp", options.length)).toBe(2);
    expect(nextMcpToolIndex(-1, "ArrowUp", options.length)).toBe(2);
    expect(nextMcpToolIndex(1, "Enter", options.length)).toBe(1);
    expect(mcpToolConfig(options[2])).toEqual({
      server_id: "github-2",
      tool_name: "create_issue",
    });
  });

  it("returns no matches and leaves unavailable permission metadata unknown", () => {
    const options = mcpToolOptions([
      {
        id: "server",
        name: "Server",
        runnable_tools: ["tool"],
        runnable_schemas: { tool: {} },
      },
    ]);
    expect(filterMcpToolOptions(options, "not found")).toEqual([]);
    expect(options[0].readOnly).toBeNull();
  });
});
