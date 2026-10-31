import { UsagePanel, type Usage } from "@/features/workspace/usage-panel";
import { serverApi } from "@/lib/api/server";
import type { SessionData } from "@/lib/api/types";
export default async function Page({
  params,
}: {
  params: Promise<{ workspaceId: string }>;
}) {
  const { workspaceId } = await params;
  const [data, session] = await Promise.all([
    serverApi<Usage>(`/workspaces/${workspaceId}/usage`),
    serverApi<SessionData>("/auth/session"),
  ]);
  const role = session.workspaces.find((w) => w.id === workspaceId)?.role;
  return (
    <UsagePanel
      workspaceId={workspaceId}
      initial={data}
      canManage={role === "owner" || role === "admin"}
    />
  );
}
