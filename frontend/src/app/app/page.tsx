import { redirect } from "next/navigation";
import { serverApi } from "@/lib/api/server";
import type { SessionData } from "@/lib/api/types";
export default async function OpenApp() {
  const session = await serverApi<SessionData>("/auth/session");
  redirect(
    session.workspaces.length
      ? `/w/${session.workspaces[0].id}/overview`
      : "/workspaces",
  );
}
