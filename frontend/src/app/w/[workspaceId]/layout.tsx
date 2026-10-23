import { notFound } from "next/navigation";
import { serverApi } from "@/lib/api/server";
import type { SessionData } from "@/lib/api/types";
import { AppShell } from "@/components/shared/app-shell";
export default async function WorkspaceLayout({
  children,
  params,
}: {
  children: React.ReactNode;
  params: Promise<{ workspaceId: string }>;
}) {
  const { workspaceId } = await params;
  const session = await serverApi<SessionData>("/auth/session");
  const workspace = session.workspaces.find((w) => w.id === workspaceId);
  if (!workspace) notFound();
  return (
    <AppShell session={session} workspace={workspace}>
      {children}
    </AppShell>
  );
}
