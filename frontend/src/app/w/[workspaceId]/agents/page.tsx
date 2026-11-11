import { serverApi } from "@/lib/api/server";
import type { SessionData } from "@/lib/api/types";
import { AgentLibrary, type LibraryAgent } from "@/features/agents/agent-library";
export default async function Agents({
  params,
}: {
  params: Promise<{ workspaceId: string }>;
}) {
  const { workspaceId } = await params;
  const [data, session] = await Promise.all([
    serverApi<{ items: LibraryAgent[] }>(`/workspaces/${workspaceId}/agents/library`),
    serverApi<SessionData>("/auth/session"),
  ]);
  const role = session.workspaces.find((workspace) => workspace.id === workspaceId)?.role;
  return <AgentLibrary agents={data.items} workspaceId={workspaceId} canEdit={role !== "viewer"} />;
}
