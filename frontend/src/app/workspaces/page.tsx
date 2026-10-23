import { serverApi } from "@/lib/api/server";
import type { SessionData } from "@/lib/api/types";
import { WorkspaceStart } from "@/features/workspace/workspace-start";
export default async function Page() {
  return (
    <WorkspaceStart session={await serverApi<SessionData>("/auth/session")} />
  );
}
