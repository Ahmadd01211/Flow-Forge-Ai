import { AgentEditor } from "@/features/agents/agent-editor";
import { serverApi } from "@/lib/api/server";
import type { ConnectionList, SessionData } from "@/lib/api/types";
import type { ToolEntry } from "@/features/tools/tool-registry";
import type { HttpTool } from "@/features/tools/http-tool-registry";
export default async function NewAgent({
  params,
}: {
  params: Promise<{ workspaceId: string }>;
}) {
  const { workspaceId } = await params;
  const [connections, session, tools, mcp, http] = await Promise.all([
    serverApi<ConnectionList>(`/workspaces/${workspaceId}/integrations`),
    serverApi<SessionData>("/auth/session"),
    serverApi<{ items: ToolEntry[] }>(`/workspaces/${workspaceId}/tools`),
    serverApi<{ items: { id: string; name: string; runnable_tools: string[]; runnable_schemas: Record<string, unknown> }[] }>(`/workspaces/${workspaceId}/mcp`),
    serverApi<{ items: HttpTool[] }>(`/workspaces/${workspaceId}/http-tools`),
  ]);
  return (
    <AgentEditor
      workspaceId={workspaceId}
      connections={connections.items}
      tools={tools.items}
      mcpServers={mcp.items}
      httpTools={http.items}
      canEdit={
        session.workspaces.find((w) => w.id === workspaceId)?.role !== "viewer"
      }
    />
  );
}
