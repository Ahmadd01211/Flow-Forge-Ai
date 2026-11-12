import { loadRecipeSample } from "@/features/templates/recipe-handoff";
import { serverApi } from "@/lib/api/server";
import type {
  ConnectionList,
  ToolOption,
  Workflow,
  SessionData,
} from "@/lib/api/types";
import { WorkflowBuilder } from "@/features/workflows/workflow-builder";
import type { HttpTool } from "@/features/tools/http-tool-registry";
import type { components } from "@/lib/api/generated";
import type { SkillItem } from "@/features/agents/skills-model";
import type { McpServerOption } from "@/features/agents/model-tools";
export default async function EditWorkflow({
  params,
  searchParams,
}: {
  searchParams: Promise<{ recipe?: string | string[] }>;
  params: Promise<{ workspaceId: string; workflowId: string }>;
}) {
  const { workspaceId, workflowId } = await params;
  const [
    workflow,
    options,
    versions,
    mcp,
    tools,
    http,
    calls,
    connections,
    skills,
    session,
  ] = await Promise.all([
    serverApi<Workflow>(`/workspaces/${workspaceId}/workflows/${workflowId}`),
    serverApi<{
      items: {
        id: string;
        name: string;
        number: number;
        provider: string;
        model_id: string;
        tool_keys: string[];
      }[];
    }>(`/workspaces/${workspaceId}/agents/workflow-options`),
    serverApi<{ items: { id: string; source_revision: number }[] }>(
      `/workspaces/${workspaceId}/workflows/${workflowId}/versions`,
    ),
    serverApi<{ items: McpServerOption[] }>(`/workspaces/${workspaceId}/mcp`),
    serverApi<{ items: ToolOption[] }>(`/workspaces/${workspaceId}/tools`),
    serverApi<{ items: HttpTool[] }>(`/workspaces/${workspaceId}/http-tools`),
    serverApi<components["schemas"]["WorkflowCallOptions"]>(
      `/workspaces/${workspaceId}/workflows/call-options?exclude_workflow_id=${workflowId}`,
    ),
    serverApi<ConnectionList>(`/workspaces/${workspaceId}/integrations`),
    serverApi<{ items: SkillItem[] }>(`/workspaces/${workspaceId}/skills`),
    serverApi<SessionData>("/auth/session"),
  ]);
  const query = await searchParams;
  const recipeSample = await loadRecipeSample(
    query.recipe,
    "workflow",
    serverApi,
  );
  return (
    <WorkflowBuilder
      recipeSample={recipeSample}
      canEdit={
        session.workspaces.find((w) => w.id === workspaceId)?.role !== "viewer"
      }
      workflow={workflow}
      agentOptions={options.items}
      mcpOptions={mcp.items}
      httpOptions={http.items}
      workflowOptions={calls.items}
      toolOptions={tools.items}
      connections={connections.items}
      skillOptions={skills.items}
      initialPublishedVersion={
        versions.items.find(
          (item) => item.source_revision === workflow.revision,
        )?.id || null
      }
    />
  );
}
