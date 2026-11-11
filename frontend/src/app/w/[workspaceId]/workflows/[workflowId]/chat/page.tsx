import { serverApi } from "@/lib/api/server";
import type { Workflow } from "@/lib/api/types";
import { WorkflowChat } from "@/features/workflows/workflow-chat";
export default async function ChatWithWorkflow({
  params,
}: {
  params: Promise<{ workspaceId: string; workflowId: string }>;
}) {
  const { workspaceId, workflowId } = await params;
  const workflow = await serverApi<Workflow>(`/workspaces/${workspaceId}/workflows/${workflowId}`);
  return <WorkflowChat workspaceId={workspaceId} workflowId={workflowId} name={workflow.name} />;
}
