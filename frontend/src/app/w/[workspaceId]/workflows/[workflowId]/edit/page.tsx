import { serverApi } from "@/lib/api/server";
import type { Workflow } from "@/lib/api/types";
import { WorkflowBuilder } from "@/features/workflows/workflow-builder";
export default async function EditWorkflow({
  params,
}: {
  params: Promise<{ workspaceId: string; workflowId: string }>;
}) {
  const { workspaceId, workflowId } = await params;
  const [workflow, options, versions, mcp] = await Promise.all([
    serverApi<Workflow>(`/workspaces/${workspaceId}/workflows/${workflowId}`),
    serverApi<{ items: { id: string; name: string; number: number; provider: string; model_id: string; tool_keys: string[] }[] }>(`/workspaces/${workspaceId}/agents/workflow-options`),
    serverApi<{ items: { id: string; source_revision: number }[] }>(`/workspaces/${workspaceId}/workflows/${workflowId}/versions`),
    serverApi<{ items: { id: string; name: string; runnable_tools: string[]; runnable_schemas: Record<string, unknown> }[] }>(`/workspaces/${workspaceId}/mcp`),
  ]);
  return <WorkflowBuilder workflow={workflow} agentOptions={options.items} mcpOptions={mcp.items} initialPublishedVersion={versions.items.find((item) => item.source_revision === workflow.revision)?.id || null} />;
}
