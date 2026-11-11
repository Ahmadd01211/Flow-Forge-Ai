import { serverApi } from "@/lib/api/server";
import type { ConnectionList, ToolOption, Workflow } from "@/lib/api/types";
import { WorkflowBuilder } from "@/features/workflows/workflow-builder";
import type { HttpTool } from "@/features/tools/http-tool-registry";
import type { components } from "@/lib/api/generated";
import type { SkillItem } from "@/features/agents/skills-model";
export default async function EditWorkflow({
  params,
}: {
  params: Promise<{ workspaceId: string; workflowId: string }>;
}) {
  const { workspaceId, workflowId } = await params;
  const [workflow, options, versions, mcp, tools, http, calls, connections, skills] = await Promise.all([
    serverApi<Workflow>(`/workspaces/${workspaceId}/workflows/${workflowId}`),
    serverApi<{ items: { id: string; name: string; number: number; provider: string; model_id: string; tool_keys: string[] }[] }>(`/workspaces/${workspaceId}/agents/workflow-options`),
    serverApi<{ items: { id: string; source_revision: number }[] }>(`/workspaces/${workspaceId}/workflows/${workflowId}/versions`),
    serverApi<{ items: { id: string; name: string; runnable_tools: string[]; runnable_schemas: Record<string, unknown>; tools?: { name: string; read_only: boolean }[] }[] }>(`/workspaces/${workspaceId}/mcp`),
    serverApi<{ items: ToolOption[] }>(`/workspaces/${workspaceId}/tools`),
    serverApi<{ items: HttpTool[] }>(`/workspaces/${workspaceId}/http-tools`),
    serverApi<components["schemas"]["WorkflowCallOptions"]>(`/workspaces/${workspaceId}/workflows/call-options?exclude_workflow_id=${workflowId}`),
    serverApi<ConnectionList>(`/workspaces/${workspaceId}/integrations`),
    serverApi<{ items: SkillItem[] }>(`/workspaces/${workspaceId}/skills`),
  ]);
  return <WorkflowBuilder workflow={workflow} agentOptions={options.items} mcpOptions={mcp.items} httpOptions={http.items} workflowOptions={calls.items} toolOptions={tools.items} connections={connections.items} skillOptions={skills.items} initialPublishedVersion={versions.items.find((item) => item.source_revision === workflow.revision)?.id || null} />;
}
