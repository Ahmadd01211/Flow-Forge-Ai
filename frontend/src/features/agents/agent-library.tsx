"use client";
import { useState } from "react";
import Link from "next/link";
import {
  ArrowUpRight,
  Bot,
  Clock3,
  Plus,
  Search,
  SlidersHorizontal,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge, EmptyState, PageHeader } from "@/components/shared/ui";
import type { Agent } from "@/lib/api/types";
export function AgentLibrary({
  agents,
  workspaceId,
}: {
  agents: Agent[];
  workspaceId: string;
}) {
  const [q, setQ] = useState("");
  const base = `/w/${workspaceId}/agents`,
    visible = agents.filter((a) =>
      `${a.name} ${a.description}`.toLowerCase().includes(q.toLowerCase()),
    );
  return (
    <>
      <PageHeader
        eyebrow="BUILDING BLOCKS"
        title="Your agents"
        description="Purpose-built intelligence, configured by you."
        action={
          <div className="row">
            <Button asChild variant="outline"><Link href={`/w/${workspaceId}/templates`}>Use a starter</Link></Button>
            <Button asChild><Link href={`${base}/new`}><Plus size={17} />Create agent</Link></Button>
          </div>
        }
      />
      <div className="collection-toolbar">
        <div className="collection-tabs">
          <button className="active">
            All agents <span>{agents.length}</span>
          </button>
          <span className="muted">Drafts</span>
        </div>
        <div className="search-input">
          <Search size={17} />
          <input
            aria-label="Search agents"
            placeholder="Search agents…"
            value={q}
            onChange={(e) => setQ(e.target.value)}
          />
        </div>
      </div>
      {!agents.length ? (
        <EmptyState
          icon={<Bot size={30} />}
          title="Your first agent starts with a purpose"
          action={
            <Button asChild>
              <Link href={`${base}/new`}>
                <Plus size={16} />
                Create your first agent
              </Link>
            </Button>
          }
        >
          Define what it should do, the data it needs, and the limits it should
          work within.
        </EmptyState>
      ) : !visible.length ? (
        <EmptyState icon={<Search />} title="No matching agents">
          Try another name or clear your search.
        </EmptyState>
      ) : (
        <div className="agent-grid">
          {visible.map((a) => (
            <Link href={`${base}/${a.id}`} key={a.id} className="agent-card">
              <div className="row between">
                <span className="node-icon purple">
                  <Bot size={23} />
                </span>
                <Badge>Draft · r{a.revision}</Badge>
              </div>
              <h2>{a.name}</h2>
              <p>
                {a.description ||
                  "Add a description to help your team understand this agent."}
              </p>
              <div className="agent-meta">
                <span>
                  <Clock3 size={13} />
                  {a.config.limits.timeout_seconds}s timeout
                </span>
                <span>${a.config.limits.max_cost_usd} cap</span>
              </div>
              <div className="agent-card-footer">
                <span>
                  <SlidersHorizontal size={14} />
                  {a.config.instructions
                    ? "Instructions configured"
                    : "Needs instructions"}
                </span>
                <ArrowUpRight size={17} />
              </div>
            </Link>
          ))}
        </div>
      )}
      <div className="collection-note">
        <Bot size={16} />
        <span>
          Freeze a saved draft as a test snapshot, compare its history, and
          validate example data against its schemas. Published versions with a
          supported live model can run from History.
        </span>
      </div>
    </>
  );
}
