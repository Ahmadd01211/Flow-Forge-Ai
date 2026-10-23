import { CapabilityPage } from "@/features/workspace/capability-page";
export default async function Page({
  params,
}: {
  params: Promise<{ workspaceId: string }>;
}) {
  const { workspaceId } = await params;
  return <CapabilityPage kind="usage" workspaceId={workspaceId} />;
}
