import { serverApi } from "@/lib/api/server";
import type { List, Workflow } from "@/lib/api/types";
import { WorkflowList } from "@/features/workflows/workflow-list";
export default async function Workflows({
  params,
}: {
  params: Promise<{ workspaceId: string }>;
}) {
  const { workspaceId } = await params;
  const result = await serverApi<List<Workflow>>(
    `/workspaces/${workspaceId}/workflows`,
  );
  return <WorkflowList workspaceId={workspaceId} items={result.items} />;
}
