"use client";
import { RunChat } from "@/features/workflows/workflow-chat";

export function AgentChat({ workspaceId, agentId, name }: { workspaceId: string; agentId: string; name: string }) {
  return (
    <RunChat
      title={name}
      subtitle="talks to the latest published version"
      backHref={`/w/${workspaceId}/agents/${agentId}`}
      backLabel="Back to the agent builder"
      sendPath={`/workspaces/${workspaceId}/agents/${agentId}/chat`}
      pollPath={(id) => `/workspaces/${workspaceId}/runs/${id}`}
      agentRuns={{ workspaceId }}
      emptyText="Send a message to start. Every message in this chat shares one conversation ID, so an agent with memory remembers what was said."
    />
  );
}
