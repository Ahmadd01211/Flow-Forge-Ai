import { SettingsPanel } from "@/features/workspace/settings-panel";
import { serverApi } from "@/lib/api/server";
import type { SessionData } from "@/lib/api/types";
export default async function Page({
  params,
}: {
  params: Promise<{ workspaceId: string }>;
}) {
  const { workspaceId } = await params;
  const session = await serverApi<SessionData>("/auth/session");
  return (
    <SettingsPanel
      workspaceId={workspaceId}
      session={session}
    />
  );
}
