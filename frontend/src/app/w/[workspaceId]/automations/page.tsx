import {
  AutomationsPanel,
  type Automation,
  type EligibleTrigger,
} from "@/features/automations/automations-panel";
import { serverApi } from "@/lib/api/server";
import type { SessionData } from "@/lib/api/types";

export default async function Page({
  params,
}: {
  params: Promise<{ workspaceId: string }>;
}) {
  const { workspaceId } = await params;
  const [session, rows, eligible] = await Promise.all([
    serverApi<SessionData>("/auth/session"),
    serverApi<{ items: Automation[] }>(
      `/workspaces/${workspaceId}/automations`,
    ),
    serverApi<{ items: EligibleTrigger[] }>(
      `/workspaces/${workspaceId}/automations/eligible`,
    ),
  ]);
  const role = session.workspaces.find((w) => w.id === workspaceId)?.role;
  return (
    <AutomationsPanel
      workspaceId={workspaceId}
      initial={rows.items}
      eligible={eligible.items}
      canManage={role === "owner" || role === "admin"}
    />
  );
}
