import { TemplateGallery, type TemplateEntry } from "@/features/templates/template-gallery";
import { serverApi } from "@/lib/api/server";
import type { SessionData } from "@/lib/api/types";

export default async function Page({
  params,
  searchParams,
}: {
  params: Promise<{ workspaceId: string }>;
  searchParams: Promise<{ focus?: string }>;
}) {
  const [{ workspaceId }, { focus }] = await Promise.all([params, searchParams]);
  const [catalog, session] = await Promise.all([
    serverApi<{ items: TemplateEntry[] }>("/templates"),
    serverApi<SessionData>("/auth/session"),
  ]);
  return <TemplateGallery workspaceId={workspaceId} templates={catalog.items} canCreate={session.workspaces.find((w) => w.id === workspaceId)?.role !== "viewer"} focus={focus} />;
}
