"use client";
import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { BookOpen, Check, LoaderCircle, Plus, Search, Wrench } from "lucide-react";
import { Button } from "@/components/ui/button";
import { EmptyState, ErrorNotice, PageHeader } from "@/components/shared/ui";
import { api } from "@/lib/api/client";
import { AgentsTabs } from "./agents-tabs";
import { groupStarters, type SkillItem, type StarterSkill } from "./skills-model";

const STATUS = {
  draft: { label: "Draft", tone: "draft" },
  published: { label: "Published", tone: "live" },
  changed: { label: "Unpublished changes", tone: "changed" },
} as const;

export function SkillLibrary({ workspaceId, skills, starters, canEdit }: { workspaceId: string; skills: SkillItem[]; starters: StarterSkill[]; canEdit: boolean }) {
  const router = useRouter();
  const base = `/w/${workspaceId}/agents/skills`;
  const [query, setQuery] = useState("");
  const [busy, setBusy] = useState(""), [error, setError] = useState("");
  const visible = skills.filter((skill) => `${skill.name} ${skill.description}`.toLowerCase().includes(query.toLowerCase()));
  const emoji = Object.fromEntries(starters.map((starter) => [starter.key, starter.emoji]));

  async function create(path: string, key: string) {
    setBusy(key);
    setError("");
    try {
      const skill = await api<{ id: string }>(`/workspaces/${workspaceId}/skills${path}`, { method: "POST", body: path ? undefined : JSON.stringify({ name: "New skill" }) });
      router.push(`${base}/${skill.id}`);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not create the skill.");
      setBusy("");
    }
  }

  return (
    <>
      <PageHeader
        eyebrow="AGENTS"
        title="Skills"
        description="Reusable know-how your agents load when they need it: policies, tone, procedures and the tools they use."
        action={canEdit && <Button onClick={() => create("", "new")} disabled={!!busy}>{busy === "new" ? <LoaderCircle size={16} className="spin" /> : <Plus size={17} />}New skill</Button>}
      />
      <AgentsTabs workspaceId={workspaceId} active="skills" />
      {error && <ErrorNotice message={error} />}
      {skills.length > 0 && (
        <>
          <div className="collection-toolbar">
            <span className="muted">{skills.length} skill{skills.length === 1 ? "" : "s"} in this workspace</span>
            <div className="search-input">
              <Search size={17} />
              <input aria-label="Search skills" placeholder="Search skills…" value={query} onChange={(event) => setQuery(event.target.value)} />
            </div>
          </div>
          <div className="library-grid">
            {visible.map((skill) => (
              <Link key={skill.id} href={`${base}/${skill.id}`} className="library-card skill-card">
                <div className="library-card-main">
                  <div className="row between">
                    <span className="skill-emoji" aria-hidden="true">{(skill.starter_key && emoji[skill.starter_key]) || "📘"}</span>
                    <span className={`builder-status ${STATUS[skill.status].tone}`}>{STATUS[skill.status].label}{skill.latest ? ` · v${skill.latest.number}` : ""}</span>
                  </div>
                  <h2>{skill.name}</h2>
                  <p>{skill.description || "Describe when an agent should use this skill."}</p>
                  <div className="library-chips">
                    {!!skill.tool_count && <span className="library-chip"><Wrench size={11} /> {skill.tool_count} tool{skill.tool_count === 1 ? "" : "s"}</span>}
                    {skill.config.examples.length > 0 && <span className="library-chip">{skill.config.examples.length} example{skill.config.examples.length === 1 ? "" : "s"}</span>}
                  </div>
                  <div className="library-health">
                    {skill.used_by.length ? <span>Used by {skill.used_by.slice(0, 2).join(", ")}{skill.used_by.length > 2 ? ` +${skill.used_by.length - 2}` : ""}</span> : <span className="muted">Not attached to an agent yet</span>}
                  </div>
                </div>
              </Link>
            ))}
          </div>
        </>
      )}
      {!skills.length && (
        <EmptyState icon={<BookOpen size={30} />} title="Teach your agents once, reuse everywhere">
          Add a starter below or write your own. Attach skills to agents and LLM steps; the model loads a skill only when a request needs it.
        </EmptyState>
      )}
      <section className="skill-starters" aria-label="Starter skills">
        <h2>Starter skills</h2>
        <p className="muted">Add one, then edit it to match how your team works.</p>
        {groupStarters(starters).map(([group, items]) => (
          <div key={group} className="skill-starter-group">
            <h3>{group}</h3>
            <div className="skill-starter-grid">
              {items.map((starter) => (
                <div key={starter.key} className={`skill-starter ${starter.added ? "added" : ""}`}>
                  <span aria-hidden="true">{starter.emoji}</span>
                  <span className="skill-starter-text">
                    <strong>{starter.name}</strong>
                    <small>{starter.description}</small>
                  </span>
                  {starter.added ? (
                    <span className="skill-starter-added"><Check size={13} /> Added</span>
                  ) : (
                    <Button size="sm" variant="outline" disabled={!canEdit || !!busy} onClick={() => create(`/starters/${starter.key}`, starter.key)}>
                      {busy === starter.key ? <LoaderCircle size={13} className="spin" /> : <Plus size={13} />} Add
                    </Button>
                  )}
                </div>
              ))}
            </div>
          </div>
        ))}
      </section>
    </>
  );
}
