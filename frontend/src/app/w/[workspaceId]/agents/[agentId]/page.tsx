import { loadRecipeSample } from "@/features/templates/recipe-handoff";
import { AgentEditor } from "@/features/agents/agent-editor";
import { serverApi } from "@/lib/api/server";
import type {
  Agent,
  ConnectionList,
  VersionList,
  SessionData,
} from "@/lib/api/types";
import type { ToolEntry } from "@/features/tools/tool-registry";
import type { HttpTool } from "@/features/tools/http-tool-registry";
import type { McpListing } from "@/features/workspace/mcp-connections";
import type { SkillItem } from "@/features/agents/skills-model";
export default async function AgentDetail({
  params,
  searchParams,
}: {
  params: Promise<{ workspaceId: string; agentId: string }>;
  searchParams: Promise<{ tab?: string; recipe?: string | string[] }>;
}) {
  const { workspaceId, agentId } = await params;
  const [
    agent,
    versions,
    session,
    connections,
    tools,
    mcp,
    http,
    skillList,
    query,
  ] = await Promise.all([
    serverApi<Agent>(`/workspaces/${workspaceId}/agents/${agentId}`),
    serverApi<VersionList>(
      `/workspaces/${workspaceId}/agents/${agentId}/versions`,
    ),
    serverApi<SessionData>("/auth/session"),
    serverApi<ConnectionList>(`/workspaces/${workspaceId}/integrations`),
    serverApi<{ items: ToolEntry[] }>(`/workspaces/${workspaceId}/tools`),
    serverApi<McpListing>(`/workspaces/${workspaceId}/mcp`),
    serverApi<{ items: HttpTool[] }>(`/workspaces/${workspaceId}/http-tools`),
    serverApi<{ items: SkillItem[] }>(`/workspaces/${workspaceId}/skills`),
    searchParams,
  ]);
  const recipeSample = await loadRecipeSample(query.recipe, "agent", serverApi);
  return (
    <AgentEditor
      recipeSample={recipeSample}
      key={`${agent.id}-${agent.revision}`}
      workspaceId={workspaceId}
      agent={agent}
      versions={versions}
      connections={connections.items}
      tools={tools.items}
      mcpServers={mcp.items}
      httpTools={http.items}
      initialTab={query.tab === "versions" ? "versions" : "instructions"}
      mcpListing={mcp}
      skills={skillList.items}
      canEdit={
        session.workspaces.find((w) => w.id === workspaceId)?.role !== "viewer"
      }
      canManage={["owner", "admin"].includes(
        session.workspaces.find((w) => w.id === workspaceId)?.role ?? "",
      )}
    />
  );
}
