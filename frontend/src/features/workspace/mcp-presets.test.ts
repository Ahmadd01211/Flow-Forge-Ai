import { describe, expect, it } from "vitest";
import { githubMcpName, githubMcpUrl } from "./mcp-presets";

describe("GitHub MCP preset", () => {
  it("matches GitHub's documented toolset URLs", () => {
    expect(githubMcpUrl("", false)).toBe("https://api.githubcopilot.com/mcp/");
    expect(githubMcpUrl("", true)).toBe("https://api.githubcopilot.com/mcp/readonly");
    expect(githubMcpUrl("issues", false)).toBe("https://api.githubcopilot.com/mcp/x/issues");
    expect(githubMcpUrl("issues", true)).toBe("https://api.githubcopilot.com/mcp/x/issues/readonly");
  });

  it("names the server after its toolset", () => {
    expect(githubMcpName("pull_requests", true)).toBe("GitHub · Pull requests (read-only)");
    expect(githubMcpName("", false)).toBe("GitHub · Default");
  });
});
