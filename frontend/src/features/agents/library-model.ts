/** Agent library summaries from GET /workspaces/{id}/agents/library, and their filters. */

export interface LibraryAgent {
  id: string;
  name: string;
  description: string;
  revision: number;
  updated_at: string;
  provider: string;
  model_id: string;
  tools: { builtin: string[]; mcp_servers: string[]; http: string[]; count: number };
  memory: boolean;
  status: "draft" | "published" | "changed";
  published: { version_id: string; number: number; runnable: boolean; chat_ready: boolean } | null;
  last_run: { state: string; created_at: string } | null;
  week: { completed: number; failed: number };
}

export type Filter = "all" | "published" | "draft" | "attention";

/** Needs attention: unpublished edits, a published version that can't run, or failures this week. */
export function needsAttention(agent: LibraryAgent): boolean {
  return agent.status === "changed" || (agent.published !== null && !agent.published.runnable) || agent.week.failed > 0;
}

export function matches(agent: LibraryAgent, filter: Filter, query: string): boolean {
  const text = `${agent.name} ${agent.description} ${agent.model_id} ${agent.tools.mcp_servers.join(" ")}`.toLowerCase();
  if (query && !text.includes(query.toLowerCase())) return false;
  if (filter === "published") return agent.status !== "draft";
  if (filter === "draft") return agent.status === "draft";
  if (filter === "attention") return needsAttention(agent);
  return true;
}
