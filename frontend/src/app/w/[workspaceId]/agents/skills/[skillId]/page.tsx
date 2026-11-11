import { serverApi } from "@/lib/api/server";
import type { SessionData } from "@/lib/api/types";
import type { ToolEntry } from "@/features/tools/tool-registry";
import type { HttpTool } from "@/features/tools/http-tool-registry";
import type { McpListing } from "@/features/workspace/mcp-connections";
import { SkillEditor } from "@/features/agents/skill-editor";
import type { SkillItem } from "@/features/agents/skills-model";

export default async function SkillDetail({ params }: { params: Promise<{ workspaceId: string; skillId: string }> }) {
  const { workspaceId, skillId } = await params;
  const [skill, versions, session, tools, mcp, http] = await Promise.all([
    serverApi<SkillItem>(`/workspaces/${workspaceId}/skills/${skillId}`),
    serverApi<{ items: { id: string; number: number; created_at: string }[] }>(`/workspaces/${workspaceId}/skills/${skillId}/versions`),
    serverApi<SessionData>("/auth/session"),
    serverApi<{ items: ToolEntry[] }>(`/workspaces/${workspaceId}/tools`),
    serverApi<McpListing>(`/workspaces/${workspaceId}/mcp`),
    serverApi<{ items: HttpTool[] }>(`/workspaces/${workspaceId}/http-tools`),
  ]);
  const role = session.workspaces.find((workspace) => workspace.id === workspaceId)?.role;
  return (
    <SkillEditor
      key={`${skill.id}-${skill.revision}-${skill.latest?.number ?? 0}`}
      workspaceId={workspaceId}
      skill={skill}
      versions={versions.items}
      tools={tools.items}
      mcpServers={mcp.items}
      httpTools={http.items}
      canEdit={role !== "viewer"}
    />
  );
}
