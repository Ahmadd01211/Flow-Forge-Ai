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
export default async function AgentDetail({
  params,
  searchParams,
}: {
  params: Promise<{ workspaceId: string; agentId: string }>;
  searchParams: Promise<{ tab?: string }>;
}) {
  const { workspaceId, agentId } = await params;
  const [agent, versions, session, connections, tools, mcp, http, query] = await Promise.all([
    serverApi<Agent>(`/workspaces/${workspaceId}/agents/${agentId}`),
    serverApi<VersionList>(
      `/workspaces/${workspaceId}/agents/${agentId}/versions`,
    ),
    serverApi<SessionData>("/auth/session"),
    serverApi<ConnectionList>(`/workspaces/${workspaceId}/integrations`),
    serverApi<{ items: ToolEntry[] }>(`/workspaces/${workspaceId}/tools`),
    serverApi<{ items: { id: string; name: string; runnable_tools: string[]; runnable_schemas: Record<string, unknown> }[] }>(`/workspaces/${workspaceId}/mcp`),
    serverApi<{ items: HttpTool[] }>(`/workspaces/${workspaceId}/http-tools`),
    searchParams,
  ]);
  return (
    <AgentEditor
      key={`${agent.id}-${agent.revision}`}
      workspaceId={workspaceId}
      agent={agent}
      versions={versions}
      connections={connections.items}
      tools={tools.items}
      mcpServers={mcp.items}
      httpTools={http.items}
      initialTab={query.tab === "versions" ? "versions" : "instructions"}
      canEdit={
        session.workspaces.find((w) => w.id === workspaceId)?.role !== "viewer"
      }
    />
  );
}
