import { RunConsole } from "@/features/executions/run-console";
import { serverApi } from "@/lib/api/server";
import type { AgentVersion, RunList, SessionData } from "@/lib/api/types";
export default async function Page({
  params,
  searchParams,
}: {
  params: Promise<{ workspaceId: string }>;
  searchParams: Promise<{ agentId?: string; versionId?: string }>;
}) {
  const { workspaceId } = await params;
  const query = await searchParams;
  const [runs, session, version] = await Promise.all([
    serverApi<RunList>(`/workspaces/${workspaceId}/runs`),
    serverApi<SessionData>("/auth/session"),
    query.agentId && query.versionId
      ? serverApi<AgentVersion>(
          `/workspaces/${workspaceId}/agents/${query.agentId}/versions/${query.versionId}`,
        )
      : Promise.resolve(null),
  ]);
  return (
    <RunConsole
      workspaceId={workspaceId}
      initialRuns={runs.items}
      version={version}
      canRun={session.workspaces.find((w) => w.id === workspaceId)?.role !== "viewer"}
    />
  );
}
