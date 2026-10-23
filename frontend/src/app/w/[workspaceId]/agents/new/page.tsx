import { AgentEditor } from "@/features/agents/agent-editor";
import { serverApi } from "@/lib/api/server";
import type { ConnectionList, SessionData } from "@/lib/api/types";
import type { ToolEntry } from "@/features/tools/tool-registry";
export default async function NewAgent({
  params,
}: {
  params: Promise<{ workspaceId: string }>;
}) {
  const { workspaceId } = await params;
  const [connections, session, tools] = await Promise.all([
    serverApi<ConnectionList>(`/workspaces/${workspaceId}/integrations`),
    serverApi<SessionData>("/auth/session"),
    serverApi<{ items: ToolEntry[] }>(`/workspaces/${workspaceId}/tools`),
  ]);
  return (
    <AgentEditor
      workspaceId={workspaceId}
      connections={connections.items}
      tools={tools.items}
      canEdit={
        session.workspaces.find((w) => w.id === workspaceId)?.role !== "viewer"
      }
    />
  );
}
