import { serverApi } from "@/lib/api/server";
import type { SessionData } from "@/lib/api/types";
import { SkillLibrary } from "@/features/agents/skill-library";
import type { SkillItem, StarterSkill } from "@/features/agents/skills-model";

export default async function Skills({ params }: { params: Promise<{ workspaceId: string }> }) {
  const { workspaceId } = await params;
  const [skills, starters, session] = await Promise.all([
    serverApi<{ items: SkillItem[] }>(`/workspaces/${workspaceId}/skills`),
    serverApi<{ items: StarterSkill[] }>(`/workspaces/${workspaceId}/skills/starters`),
    serverApi<SessionData>("/auth/session"),
  ]);
  const role = session.workspaces.find((workspace) => workspace.id === workspaceId)?.role;
  return <SkillLibrary workspaceId={workspaceId} skills={skills.items} starters={starters.items} canEdit={role !== "viewer"} />;
}
