import { serverApi } from "@/lib/api/server";
import type { SessionData } from "@/lib/api/types";
import { RunTrace } from "@/features/executions/run-trace";
import type { TraceData } from "@/features/executions/trace-model";

export default async function RunTracePage({ params }: { params: Promise<{ workspaceId: string; runId: string }> }) {
  const { workspaceId, runId } = await params;
  const [trace, session] = await Promise.all([
    serverApi<TraceData>(`/workspaces/${workspaceId}/runs/${runId}/trace`),
    serverApi<SessionData>("/auth/session"),
  ]);
  const role = session.workspaces.find((workspace) => workspace.id === workspaceId)?.role;
  return <RunTrace workspaceId={workspaceId} trace={trace} canEdit={role !== "viewer"} />;
}
