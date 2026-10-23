import { serverApi } from "@/lib/api/server";
import type { Agent, List } from "@/lib/api/types";
import { AgentLibrary } from "@/features/agents/agent-library";
export default async function Agents({
  params,
}: {
  params: Promise<{ workspaceId: string }>;
}) {
  const { workspaceId } = await params;
  const data = await serverApi<List<Agent>>(
    `/workspaces/${workspaceId}/agents`,
  );
  return <AgentLibrary agents={data.items} workspaceId={workspaceId} />;
}
