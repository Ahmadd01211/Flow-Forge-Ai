import { TemplateGallery, type TemplateEntry } from "@/features/templates/template-gallery";
import { serverApi } from "@/lib/api/server";
import type { SessionData } from "@/lib/api/types";

export default async function Page({ params }: { params: Promise<{ workspaceId: string }> }) {
  const { workspaceId } = await params;
  const [catalog, session] = await Promise.all([
    serverApi<{ items: TemplateEntry[] }>("/templates"),
    serverApi<SessionData>("/auth/session"),
  ]);
  return <TemplateGallery workspaceId={workspaceId} templates={catalog.items} canCreate={session.workspaces.find((w) => w.id === workspaceId)?.role !== "viewer"} />;
}
