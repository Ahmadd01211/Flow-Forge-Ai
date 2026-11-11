import Link from "next/link";
import { Bot, BookOpen } from "lucide-react";

/** Agents and Skills share one tab in the sidebar. */
export function AgentsTabs({ workspaceId, active }: { workspaceId: string; active: "agents" | "skills" }) {
  const base = `/w/${workspaceId}/agents`;
  return (
    <nav className="agents-tabs" aria-label="Agents and skills">
      <Link href={base} className={active === "agents" ? "active" : ""} aria-current={active === "agents" ? "page" : undefined}><Bot size={15} /> Agents</Link>
      <Link href={`${base}/skills`} className={active === "skills" ? "active" : ""} aria-current={active === "skills" ? "page" : undefined}><BookOpen size={15} /> Skills</Link>
    </nav>
  );
}
