import { serverApi } from "@/lib/api/server";
import type { Agent } from "@/lib/api/types";
import { AgentChat } from "@/features/agents/agent-chat";

export default async function ChatWithAgent({
  params,
}: {
  params: Promise<{ workspaceId: string; agentId: string }>;
}) {
  const { workspaceId, agentId } = await params;
  const agent = await serverApi<Agent>(`/workspaces/${workspaceId}/agents/${agentId}`);
  return <AgentChat workspaceId={workspaceId} agentId={agentId} name={agent.name} />;
}
