import { TaskStart } from "@/features/workspace/task-start";

export default async function Page({
  params,
}: {
  params: Promise<{ workspaceId: string }>;
}) {
  const { workspaceId } = await params;
  return <TaskStart workspaceId={workspaceId} />;
}
