/** GitHub's hosted MCP server exposes one URL per toolset, each with a /readonly variant. */
export const GITHUB_TOOLSETS = [
  ["", "Default (repositories, issues, pull requests, users)"],
  ["issues", "Issues"],
  ["pull_requests", "Pull requests"],
  ["repos", "Repositories and files"],
  ["actions", "Actions (CI/CD)"],
  ["notifications", "Notifications"],
  ["discussions", "Discussions"],
  ["all", "All GitHub tools"],
] as const;

export type GithubToolset = (typeof GITHUB_TOOLSETS)[number][0];

export function githubMcpUrl(toolset: GithubToolset, readOnly: boolean): string {
  const base = toolset
    ? `https://api.githubcopilot.com/mcp/x/${toolset}`
    : "https://api.githubcopilot.com/mcp";
  return readOnly ? `${base}/readonly` : toolset ? base : `${base}/`;
}

export function githubMcpName(toolset: GithubToolset, readOnly: boolean): string {
  const label = GITHUB_TOOLSETS.find(([key]) => key === toolset)?.[1] ?? "";
  const short = toolset ? label : "Default";
  return `GitHub · ${short}${readOnly ? " (read-only)" : ""}`.slice(0, 100);
}

export const DEEPWIKI_MCP_URL = "https://mcp.deepwiki.com/mcp";
