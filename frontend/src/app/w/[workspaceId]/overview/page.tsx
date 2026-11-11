import Link from "next/link";
import { ArrowRight, Bot, LayoutGrid, Plus, Sparkles, Terminal, Workflow } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge, PageHeader } from "@/components/shared/ui";
import { serverApi } from "@/lib/api/server";
import type { SessionData } from "@/lib/api/types";
import { Attention, OverviewDashboard, SetupChecklist } from "@/features/workspace/overview-dashboard";
import type { OverviewData } from "@/features/workspace/overview-model";

export default async function Overview({
  params,
  searchParams,
}: {
  params: Promise<{ workspaceId: string }>;
  searchParams: Promise<{ view?: string }>;
}) {
  const [{ workspaceId }, { view }] = await Promise.all([params, searchParams]);
  const base = `/w/${workspaceId}`;
  const [data, session] = await Promise.all([
    serverApi<OverviewData>(`/workspaces/${workspaceId}/overview`),
    serverApi<SessionData>("/auth/session"),
  ]);
  // New workspaces get the guided view until setup is done; either view can be opened by link.
  const showSetup = view === "setup" || (!data.setup.complete && view !== "dashboard");
  const canEdit = data.role !== "viewer";
  return (
    <>
      <PageHeader
        eyebrow="YOUR AUTOMATION WORKSPACE"
        title={`Welcome, ${session.user.name.split(" ")[0]}`}
        description={showSetup ? "Turn your next good idea into a workflow that works." : "Here's what's happening in your workspace."}
        action={
          canEdit && (
            <div className="row overview-actions">
              <Button asChild variant="outline">
                <Link href={`${base}/templates`}><LayoutGrid size={16} />From template</Link>
              </Button>
              <Button asChild variant="outline">
                <Link href={`${base}/agents/new`}><Bot size={16} />New agent</Link>
              </Button>
              <Button asChild>
                <Link href={`${base}/workflows`}><Plus size={17} />New workflow</Link>
              </Button>
            </div>
          )
        }
      />
      {showSetup ? (
        <>
          {/* Decisions and breakages matter even before setup is finished. */}
          <Attention data={data} base={base} workspaceId={workspaceId} />
          <div className="overview-hero">
            <div>
              <Badge tone="purple"><Sparkles size={12} /> BUILD SOMETHING USEFUL</Badge>
              <h2>One workflow.<br />A world of possibilities.</h2>
              <p>Connect a model, publish a workflow, and choose how it starts.<br />The checklist below follows your progress.</p>
              <Button asChild>
                <Link href={`${base}/workflows`}>Open your workflows <ArrowRight size={16} /></Link>
              </Button>
            </div>
            <div className="overview-flow" aria-hidden="true">
              <div className="overview-flow-node"><span className="node-icon teal"><Terminal size={21} /></span><span>Trigger</span></div>
              <span className="flow-line" />
              <div className="overview-flow-node featured"><span className="node-icon purple"><Bot size={26} /></span><span>LLM or agent</span><small>Tools, APIs, memory</small></div>
              <span className="flow-line" />
              <div className="overview-flow-node"><span className="node-icon blue"><Workflow size={21} /></span><span>Outcome</span></div>
              <span className="illustration-label">YOUR NEXT AUTOMATION STARTS HERE</span>
            </div>
          </div>
          <SetupChecklist data={data} base={base} />
          <p className="overview-footnote">
            <Link className="text-link" href={`${base}/overview?view=dashboard`}>
              {data.setup.complete ? "Back to the dashboard" : "Skip to the dashboard"} <ArrowRight size={13} />
            </Link>
          </p>
        </>
      ) : (
        <OverviewDashboard data={data} base={base} workspaceId={workspaceId} />
      )}
    </>
  );
}
