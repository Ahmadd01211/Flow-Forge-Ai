import Link from "next/link";
import { ArrowRight } from "lucide-react";
import { PageHeader } from "@/components/shared/ui";
import { Button } from "@/components/ui/button";
import { startingChoices } from "./task-start-model";

export function TaskStart({ workspaceId }: { workspaceId: string }) {
  const base = `/w/${workspaceId}`;

  return (
    <>
      <PageHeader
        eyebrow="START A NEW AUTOMATION"
        title="Choose what to build"
        description="Start with a guided task or open a blank editor. Your choices stay editable until you publish."
      />
      <div className="task-start-grid">
        {startingChoices(base).map((choice) => (
          <article className="panel task-start-card" key={choice.key}>
            <h2>{choice.title}</h2>
            <p>{choice.description}</p>
            <Button asChild>
              <Link href={choice.href}>
                {choice.key === "support-triage"
                  ? "Preview support triage"
                  : choice.key === "blank-agent"
                    ? "Create a blank agent"
                    : "Open workflows"}
                <ArrowRight size={15} />
              </Link>
            </Button>
          </article>
        ))}
      </div>
      <p className="task-start-footnote">
        Publishing and running are separate actions. Connect a provider before
        testing an agent that uses a model.
      </p>
    </>
  );
}
