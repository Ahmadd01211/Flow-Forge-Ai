import { ProviderConnection } from "@/features/workspace/provider-connection";
import { McpConnections, type McpListing } from "@/features/workspace/mcp-connections";
import { serverApi } from "@/lib/api/server";
import type { ConnectionList, SessionData } from "@/lib/api/types";

export default async function Page({
  params,
}: {
  params: Promise<{ workspaceId: string }>;
}) {
  const { workspaceId } = await params;
  const [connections, session, mcp] = await Promise.all([
    serverApi<ConnectionList>(`/workspaces/${workspaceId}/integrations`),
    serverApi<SessionData>("/auth/session"),
    serverApi<McpListing>(`/workspaces/${workspaceId}/mcp`),
  ]);
  const role = session.workspaces.find((w) => w.id === workspaceId)?.role;
  return <>
    <ProviderConnection
      workspaceId={workspaceId}
      connections={connections.items}
      canManage={role === "owner" || role === "admin"}
    />
    <McpConnections workspaceId={workspaceId} initial={mcp} canManage={role === "owner" || role === "admin"} canTest={role !== "viewer"} />
  </>;
}
