"use client";
import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Archive, Bot, Brain, Copy, FlaskConical, Globe2, LayoutGrid, LoaderCircle, MessageSquare, Plug, Plus, Search, Wrench } from "lucide-react";
import { Button } from "@/components/ui/button";
import { EmptyState, ErrorNotice, PageHeader } from "@/components/shared/ui";
import { LocalTime } from "@/components/shared/local-time";
import { api } from "@/lib/api/client";
import { matches, needsAttention, type Filter, type LibraryAgent } from "./library-model";
import { AgentsTabs } from "./agents-tabs";

export type { LibraryAgent } from "./library-model";

const STATUS = {
  draft: { label: "Draft", tone: "draft" },
  published: { label: "Published", tone: "live" },
  changed: { label: "Unpublished changes", tone: "changed" },
} as const;

export function AgentLibrary({ agents, workspaceId, canEdit = true }: { agents: LibraryAgent[]; workspaceId: string; canEdit?: boolean }) {
  const router = useRouter();
  const base = `/w/${workspaceId}/agents`;
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<Filter>("all");
  const [busy, setBusy] = useState(""), [error, setError] = useState("");
  const visible = agents.filter((agent) => matches(agent, filter, query));
  const counts: Record<Filter, number> = {
    all: agents.length,
    published: agents.filter((agent) => agent.status !== "draft").length,
    draft: agents.filter((agent) => agent.status === "draft").length,
    attention: agents.filter(needsAttention).length,
  };

  async function act(agent: LibraryAgent, action: "duplicate" | "archive") {
    if (action === "archive" && !window.confirm(`Archive ${agent.name}? Published versions keep working for existing workflows and deployments.`)) return;
    setBusy(`${action}-${agent.id}`);
    setError("");
    try {
      const result = await api<{ id: string }>(`/workspaces/${workspaceId}/agents/${agent.id}/${action}`, { method: "POST" });
      if (action === "duplicate") router.push(`${base}/${result.id}`);
      else router.refresh();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "That didn't work.");
    } finally {
      setBusy("");
    }
  }

  return (
    <>
      <PageHeader
        eyebrow="AGENTS"
        title="Your agents"
        description="Give a model a purpose, tools and memory. Try it as you build."
        action={
          canEdit && (
            <div className="row">
              <Button asChild variant="outline"><Link href={`/w/${workspaceId}/templates`}><LayoutGrid size={16} />Starters</Link></Button>
              <Button asChild><Link href={`${base}/new`}><Plus size={17} />New agent</Link></Button>
            </div>
          )
        }
      />
      <AgentsTabs workspaceId={workspaceId} active="agents" />
      <div className="collection-toolbar">
        <div className="library-filters" role="tablist" aria-label="Filter agents">
          {([["all", "All"], ["published", "Published"], ["draft", "Drafts"], ["attention", "Needs attention"]] as const).map(([id, label]) => (
            <button key={id} type="button" role="tab" aria-selected={filter === id} className={filter === id ? "active" : ""} onClick={() => setFilter(id)}>
              {label} <span>{counts[id]}</span>
            </button>
          ))}
        </div>
        <div className="search-input">
          <Search size={17} />
          <input aria-label="Search agents" placeholder="Search name, model or tool…" value={query} onChange={(event) => setQuery(event.target.value)} />
        </div>
      </div>
      {error && <ErrorNotice message={error} />}
      {!agents.length ? (
        <EmptyState
          icon={<Bot size={30} />}
          title="Build your first agent"
          action={canEdit && <Button asChild><Link href={`${base}/new`}><Plus size={16} />New agent</Link></Button>}
        >
          Pick a starter like a chat assistant or ticket triage, switch on the tools it needs, and chat with it while you build.
        </EmptyState>
      ) : !visible.length ? (
        <EmptyState icon={<Search />} title="No matching agents">Try another filter or search.</EmptyState>
      ) : (
        <div className="library-grid">
          {visible.map((agent) => {
            const status = STATUS[agent.status];
            const runs = agent.week.completed + agent.week.failed;
            return (
              <article key={agent.id} className="library-card">
                <Link href={`${base}/${agent.id}`} className="library-card-main">
                  <div className="row between">
                    <span className="builder-avatar" aria-hidden="true"><Bot size={20} /></span>
                    <span className={`builder-status ${status.tone}`}>{status.label}{agent.published ? ` · v${agent.published.number}` : ""}</span>
                  </div>
                  <h2>{agent.name}</h2>
                  <p>{agent.description || "No description yet."}</p>
                  <div className="library-chips">
                    {agent.model_id ? <span className="library-chip model">{agent.model_id}</span> : <span className="library-chip muted">No model</span>}
                    {agent.tools.builtin.length > 0 && <span className="library-chip"><Wrench size={11} /> {agent.tools.builtin.length}</span>}
                    {agent.tools.mcp_servers.map((server) => <span key={server} className="library-chip"><Plug size={11} /> {server}</span>)}
                    {agent.tools.http.length > 0 && <span className="library-chip"><Globe2 size={11} /> {agent.tools.http.length} API{agent.tools.http.length === 1 ? "" : "s"}</span>}
                    {agent.memory && <span className="library-chip memory"><Brain size={11} /> Memory</span>}
                  </div>
                  <div className="library-health">
                    {agent.published && !agent.published.runnable ? (
                      <span className="warn">⚠ Provider key changed: republish to run</span>
                    ) : agent.last_run ? (
                      <span>
                        <i className={`dot ${agent.last_run.state}`} /> Last run <LocalTime value={agent.last_run.created_at} />
                        {runs > 0 && ` · ${agent.week.completed}/${runs} succeeded this week`}
                      </span>
                    ) : (
                      <span className="muted">No runs yet</span>
                    )}
                  </div>
                </Link>
                <div className="library-actions">
                  {agent.published?.chat_ready && agent.published.runnable && (
                    <Link className="library-action" href={`${base}/${agent.id}/chat`}><MessageSquare size={14} /> Chat</Link>
                  )}
                  <Link className="library-action" href={`${base}/${agent.id}`}><FlaskConical size={14} /> {canEdit ? "Build & test" : "Open"}</Link>
                  {canEdit && (
                    <>
                      <button type="button" className="library-action icon" title="Duplicate" aria-label={`Duplicate ${agent.name}`} disabled={!!busy} onClick={() => act(agent, "duplicate")}>
                        {busy === `duplicate-${agent.id}` ? <LoaderCircle size={14} className="spin" /> : <Copy size={14} />}
                      </button>
                      <button type="button" className="library-action icon" title="Archive" aria-label={`Archive ${agent.name}`} disabled={!!busy} onClick={() => act(agent, "archive")}>
                        {busy === `archive-${agent.id}` ? <LoaderCircle size={14} className="spin" /> : <Archive size={14} />}
                      </button>
                    </>
                  )}
                </div>
              </article>
            );
          })}
        </div>
      )}
    </>
  );
}
