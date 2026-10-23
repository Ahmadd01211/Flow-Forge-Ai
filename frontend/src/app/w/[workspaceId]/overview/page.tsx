import Link from "next/link";
import {
  ArrowRight,
  Bot,
  GitBranch,
  Plus,
  ShieldCheck,
  Sparkles,
  Terminal,
  Workflow,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge, ChecklistItem, PageHeader } from "@/components/shared/ui";
import { serverApi } from "@/lib/api/server";
import type { SessionData } from "@/lib/api/types";
export default async function Overview({
  params,
}: {
  params: Promise<{ workspaceId: string }>;
}) {
  const { workspaceId } = await params,
    base = `/w/${workspaceId}`;
  const [stats, session] = await Promise.all([
    serverApi<{ agents: number; workflows: number }>(
      `/workspaces/${workspaceId}/overview`,
    ),
    serverApi<SessionData>("/auth/session"),
  ]);
  return (
    <>
      <PageHeader
        eyebrow="YOUR AUTOMATION WORKSPACE"
        title={`Welcome, ${session.user.name.split(" ")[0]}`}
        description="Turn your next good idea into a workflow that works."
        action={
          <Button asChild>
            <Link href={`${base}/agents/new`}>
              <Plus size={17} />
              Create agent
            </Link>
          </Button>
        }
      />
      <div className="overview-hero">
        <div>
          <Badge tone="purple">
            <Sparkles size={12} /> BUILD SOMETHING USEFUL
          </Badge>
          <h2>
            One agent.
            <br />A world of possibilities.
          </h2>
          <p>
            Start with a clear purpose. Connect the steps.
            <br />
            Keep the whole process in view.
          </p>
          <Button asChild>
            <Link href={`${base}/workflows`}>
              Open your workflows <ArrowRight size={16} />
            </Link>
          </Button>
        </div>
        <div className="overview-flow" aria-hidden="true">
          <div className="overview-flow-node">
            <span className="node-icon teal">
              <Terminal size={21} />
            </span>
            <span>Input</span>
          </div>
          <span className="flow-line" />
          <div className="overview-flow-node featured">
            <span className="node-icon purple">
              <Bot size={26} />
            </span>
            <span>Your agent</span>
            <small>Instructions + limits</small>
          </div>
          <span className="flow-line" />
          <div className="overview-flow-node">
            <span className="node-icon blue">
              <Workflow size={21} />
            </span>
            <span>Outcome</span>
          </div>
          <span className="illustration-label">
            YOUR NEXT AUTOMATION STARTS HERE
          </span>
        </div>
      </div>
      <div className="metric-grid">
        {[
          {
            icon: Bot,
            label: "Agent drafts",
            value: stats.agents,
            note: "Configured in this workspace",
          },
          {
            icon: GitBranch,
            label: "Workflow drafts",
            value: stats.workflows,
            note: "Saved graphs ready to refine",
          },
          {
            icon: ShieldCheck,
            label: "Live execution",
            value: "Not enabled",
            note: "Runtime will follow validated definitions",
          },
        ].map((m) => (
          <article className="metric-card" key={m.label}>
            <div className="metric-label">
              {m.label}
              <m.icon size={18} />
            </div>
            <strong
              className={typeof m.value === "string" ? "metric-text" : ""}
            >
              {m.value}
            </strong>
            <p>{m.note}</p>
          </article>
        ))}
      </div>
      <div className="dashboard-grid">
        <section className="panel">
          <div className="panel-header">
            <div>
              <h2>Your first automation</h2>
              <p>A few clear steps to build your foundation.</p>
            </div>
            <Badge>
              {Math.min(1, stats.agents) + Math.min(1, stats.workflows)}/3 ready
            </Badge>
          </div>
          <ChecklistItem
            done={stats.agents > 0}
            title="Give your agent a purpose"
            description="Write instructions and set input, output and resource limits."
            action={
              <Link className="text-link" href={`${base}/agents/new`}>
                Create agent <ArrowRight size={14} />
              </Link>
            }
          />
          <ChecklistItem
            done={stats.workflows > 0}
            title="Connect a workflow"
            description="Arrange steps and inspect the graph on the canvas."
            action={
              <Link className="text-link" href={`${base}/workflows`}>
                Build workflow <ArrowRight size={14} />
              </Link>
            }
          />
          <ChecklistItem
            done={false}
            title="Test a real execution"
            description="Coming with the bounded runtime. No simulated successes."
            action={<Badge tone="amber">Next milestone</Badge>}
          />
        </section>
        <section className="panel workspace-principles">
          <div className="node-icon purple">
            <ShieldCheck size={23} />
          </div>
          <h2>Clarity at every step.</h2>
          <p>
            Definitions are saved in PostgreSQL. Workspace permissions and draft
            revision checks are enforced by the backend.
          </p>
          <div className="principle-line">
            <span /> Explicit workspace ownership
          </div>
          <div className="principle-line">
            <span /> Safe save conflict handling
          </div>
          <div className="principle-line">
            <span /> Server-side graph checks
          </div>
        </section>
      </div>
    </>
  );
}
