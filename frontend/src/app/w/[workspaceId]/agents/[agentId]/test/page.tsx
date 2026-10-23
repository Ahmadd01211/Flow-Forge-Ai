import Link from "next/link";
import { FlaskConical } from "lucide-react";
import { ContractPlayground } from "@/features/agents/contract-playground";
import { serverApi } from "@/lib/api/server";
import type { AgentVersion, VersionList, SessionData } from "@/lib/api/types";
import { EmptyState } from "@/components/shared/ui";
import { Button } from "@/components/ui/button";
export default async function TestAgent({
  params,
  searchParams,
}: {
  params: Promise<{ workspaceId: string; agentId: string }>;
  searchParams: Promise<{ version?: string }>;
}) {
  const { workspaceId, agentId } = await params,
    query = await searchParams;
  const versions = await serverApi<VersionList>(
    `/workspaces/${workspaceId}/agents/${agentId}/versions`,
  );
  const versionId = query.version || versions.items[0]?.id;
  if (!versionId)
    return (
      <EmptyState
        icon={<FlaskConical size={28} />}
        title="Create a test snapshot first"
        action={
          <Button asChild>
            <Link href={`/w/${workspaceId}/agents/${agentId}`}>
              Open agent configuration
            </Link>
          </Button>
        }
      >
        The playground validates frozen contracts, so edits cannot change the
        schema while you test it.
      </EmptyState>
    );
  const [version, session] = await Promise.all([
    serverApi<AgentVersion>(
      `/workspaces/${workspaceId}/agents/${agentId}/versions/${encodeURIComponent(versionId)}`,
    ),
    serverApi<SessionData>("/auth/session"),
  ]);
  return (
    <ContractPlayground
      version={version}
      canEdit={
        session.workspaces.find((w) => w.id === workspaceId)?.role !== "viewer"
      }
    />
  );
}
