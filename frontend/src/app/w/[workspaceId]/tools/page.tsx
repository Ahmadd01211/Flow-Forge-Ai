import { ToolRegistry, type ToolEntry } from "@/features/tools/tool-registry";
import { serverApi } from "@/lib/api/server";
import type { SessionData } from "@/lib/api/types";
export default async function Page({
  params,
}: {
  params: Promise<{ workspaceId: string }>;
}) {
  const { workspaceId } = await params;
  const [catalog, session] = await Promise.all([
    serverApi<{ items: ToolEntry[] }>(`/workspaces/${workspaceId}/tools`),
    serverApi<SessionData>("/auth/session"),
  ]);
  const role = session.workspaces.find((w) => w.id === workspaceId)?.role;
  return <ToolRegistry workspaceId={workspaceId} initialTools={catalog.items} canManage={role === "owner" || role === "admin"} canTest={role !== "viewer"} />;
}
