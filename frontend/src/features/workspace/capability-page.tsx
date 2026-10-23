import Link from "next/link";
import {
  ChartNoAxesCombined,
  GitBranch,
  ShieldCheck,
} from "lucide-react";
import { Badge, PageHeader } from "@/components/shared/ui";
import { Button } from "@/components/ui/button";
import type { SessionData } from "@/lib/api/types";
const content = {
  executions: {
    title: "Executions",
    eyebrow: "SEE WHAT HAPPENED",
    description: "An honest record of every workflow run.",
    icon: GitBranch,
    heading: "Execution monitoring comes with the runtime",
    body: "There are no live runs yet. Durable dispatch, budget enforcement and worker recovery are the next runtime milestones. Save and validate your workflow drafts in the meantime.",
  },
  usage: {
    title: "Usage & budgets",
    eyebrow: "KNOW YOUR LIMITS",
    description: "Measured usage. Visible reservations. Clear boundaries.",
    icon: ChartNoAxesCombined,
    heading: "Usage begins with real execution",
    body: "No provider calls have been made by this application. The execution ledger will distinguish measured costs, reserved budget and uncertain charges. Agent draft limits are saved now; they do not represent consumed usage.",
  },
  settings: {
    title: "Workspace settings",
    eyebrow: "YOUR TEAM’S FOUNDATION",
    description: "Workspace identity and your current permissions.",
    icon: ShieldCheck,
    heading: "Workspace identity",
    body: "Workspace ownership is enforced in FastAPI. Your session uses an opaque, HTTP-only cookie; credentials are not kept in browser storage. Member administration and security controls will arrive as independently tested slices.",
  },
};
export function CapabilityPage({
  kind,
  workspaceId,
  session,
}: {
  kind: keyof typeof content;
  workspaceId: string;
  session?: SessionData;
}) {
  const c = content[kind],
    w = session?.workspaces.find((w) => w.id === workspaceId);
  return (
    <>
      <PageHeader
        eyebrow={c.eyebrow}
        title={c.title}
        description={c.description}
      />
      <section className="panel capability-panel">
        <div className="row between">
          <span className="node-icon purple">
            <c.icon size={25} />
          </span>
          <Badge tone={kind === "settings" ? "green" : "amber"}>
            {kind === "settings" ? "Active workspace" : "Not enabled yet"}
          </Badge>
        </div>
        <h2>{c.heading}</h2>
        <p>{c.body}</p>
        {kind === "settings" && w ? (
          <div className="mt-6">
            {[
              ["Workspace", w.name],
              ["Your role", w.role],
              ["Account", session?.user.email || ""],
              ["Workspace ID", w.id],
            ].map(([k, v]) => (
              <div className="policy-line" key={k}>
                <span>{k}</span>
                <strong>{v}</strong>
              </div>
            ))}
          </div>
        ) : (
          <div className="mt-6">
            <Button asChild variant="outline">
              <Link
                href={`/w/${workspaceId}/workflows`}
              >
                <GitBranch size={15} /> Open workflows
              </Link>
            </Button>
          </div>
        )}
      </section>
    </>
  );
}
