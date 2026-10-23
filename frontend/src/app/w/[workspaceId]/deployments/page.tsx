import {
  DeploymentsPanel,
  type DeploymentEntry,
  type EligibleVersion,
} from "@/features/deployments/deployments-panel";
import { PageHeader } from "@/components/shared/ui";
import { serverApi } from "@/lib/api/server";
import type { SessionData } from "@/lib/api/types";

export default async function Page({
  params,
}: {
  params: Promise<{ workspaceId: string }>;
}) {
  const { workspaceId } = await params;
  const session = await serverApi<SessionData>("/auth/session");
  const role = session.workspaces.find(
    (workspace) => workspace.id === workspaceId,
  )?.role;
  if (role !== "owner" && role !== "admin") {
    return (
      <PageHeader
        eyebrow="HOSTED ACCESS"
        title="Deployments"
        description="A workspace owner or admin manages deployment keys and endpoints."
      />
    );
  }
  const [deployments, eligible] = await Promise.all([
    serverApi<{ items: DeploymentEntry[] }>(
      `/workspaces/${workspaceId}/deployments`,
    ),
    serverApi<{ items: EligibleVersion[] }>(
      `/workspaces/${workspaceId}/deployments/eligible`,
    ),
  ]);
  return (
    <DeploymentsPanel
      workspaceId={workspaceId}
      initialDeployments={deployments.items}
      eligibleVersions={eligible.items}
    />
  );
}
