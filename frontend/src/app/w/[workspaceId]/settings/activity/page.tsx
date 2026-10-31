import { ActivityPanel } from "@/features/workspace/activity-panel";
import { serverApi } from "@/lib/api/server";
import type { components } from "@/lib/api/generated";

export default async function Page({
  params,
}: {
  params: Promise<{ workspaceId: string }>;
}) {
  const { workspaceId } = await params;
  const initial = await serverApi<components["schemas"]["ActivityPage"]>(
    `/workspaces/${workspaceId}/activity`,
  );
  return <ActivityPanel workspaceId={workspaceId} initial={initial} />;
}
