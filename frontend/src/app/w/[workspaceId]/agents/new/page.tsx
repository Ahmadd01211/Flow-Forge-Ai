import { AgentEditor } from "@/features/agents/agent-editor";
import { serverApi } from "@/lib/api/server";
import type { ConnectionList, SessionData } from "@/lib/api/types";
import type { ToolEntry } from "@/features/tools/tool-registry";
import type { HttpTool } from "@/features/tools/http-tool-registry";
import type { McpListing } from "@/features/workspace/mcp-connections";
import type { SkillItem } from "@/features/agents/skills-model";
export default async function NewAgent({
  params,
}: {
  params: Promise<{ workspaceId: string }>;
}) {
  const { workspaceId } = await params;
  const [connections, session, tools, mcp, http, skillList] = await Promise.all([
    serverApi<ConnectionList>(`/workspaces/${workspaceId}/integrations`),
    serverApi<SessionData>("/auth/session"),
    serverApi<{ items: ToolEntry[] }>(`/workspaces/${workspaceId}/tools`),
    serverApi<McpListing>(`/workspaces/${workspaceId}/mcp`),
    serverApi<{ items: HttpTool[] }>(`/workspaces/${workspaceId}/http-tools`),
    serverApi<{ items: SkillItem[] }>(`/workspaces/${workspaceId}/skills`),
  ]);
  return (
    <AgentEditor
      workspaceId={workspaceId}
      connections={connections.items}
      tools={tools.items}
      mcpServers={mcp.items}
      httpTools={http.items}
      mcpListing={mcp}
      skills={skillList.items}
      canEdit={
        session.workspaces.find((w) => w.id === workspaceId)?.role !== "viewer"
      }
      canManage={["owner", "admin"].includes(session.workspaces.find((w) => w.id === workspaceId)?.role ?? "")}
    />
  );
}
