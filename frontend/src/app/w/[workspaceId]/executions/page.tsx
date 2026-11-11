import { RunConsole } from "@/features/executions/run-console";
import {
  WorkflowConsole,
  type WorkflowExecution,
} from "@/features/executions/workflow-console";
import Link from "next/link";
import { serverApi } from "@/lib/api/server";
import type { AgentVersion, RunList, SessionData } from "@/lib/api/types";
export default async function Page({
  params,
  searchParams,
}: {
  params: Promise<{ workspaceId: string }>;
  searchParams: Promise<{
    agentId?: string;
    versionId?: string;
    kind?: string;
    runId?: string;
  }>;
}) {
  const { workspaceId } = await params;
  const query = await searchParams;
  const [runs, session, version, workflows] = await Promise.all([
    serverApi<RunList>(`/workspaces/${workspaceId}/runs`),
    serverApi<SessionData>("/auth/session"),
    query.agentId && query.versionId
      ? serverApi<AgentVersion>(
          `/workspaces/${workspaceId}/agents/${query.agentId}/versions/${query.versionId}`,
        )
      : Promise.resolve(null),
    query.kind === "workflows"
      ? serverApi<{ items: WorkflowExecution[] }>(
          `/workspaces/${workspaceId}/workflow-runs`,
        )
      : Promise.resolve({ items: [] }),
  ]);
  return (
    <>
      <nav className="execution-tabs" aria-label="Execution type">
        <Link
          href={`/w/${workspaceId}/executions`}
          aria-current={query.kind !== "workflows" ? "page" : undefined}
        >
          Agent runs
        </Link>
        <Link
          href={`/w/${workspaceId}/executions?kind=workflows`}
          aria-current={query.kind === "workflows" ? "page" : undefined}
        >
          Workflow runs
        </Link>
      </nav>
      {query.kind === "workflows" ? (
        <WorkflowConsole
          userId={session.user.id}
          canReview={["owner", "admin"].includes(
            session.workspaces.find((w) => w.id === workspaceId)?.role || "",
          )}
          workspaceId={workspaceId}
          initial={workflows.items}
          initialSelected={query.runId}
          canRun={
            session.workspaces.find((w) => w.id === workspaceId)?.role !==
            "viewer"
          }
        />
      ) : (
        <RunConsole
          workspaceId={workspaceId}
          initialRuns={runs.items}
          version={version}
          canRun={
            session.workspaces.find((w) => w.id === workspaceId)?.role !==
            "viewer"
          }
        />
      )}
    </>
  );
}
