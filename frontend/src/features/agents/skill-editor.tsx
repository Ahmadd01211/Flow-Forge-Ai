"use client";
import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ArrowLeft, Archive, Check, LoaderCircle, Plus, Rocket, Save, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ErrorNotice } from "@/components/shared/ui";
import { LocalTime } from "@/components/shared/local-time";
import { api } from "@/lib/api/client";
import { useUnsavedChanges } from "@/lib/use-unsaved-changes";
import type { AgentConfig } from "@/lib/api/types";
import type { ToolEntry } from "@/features/tools/tool-registry";
import type { HttpTool } from "@/features/tools/http-tool-registry";
import type { McpServerOption } from "./model-tools";
import { ToolShelf } from "./tool-shelf";
import type { SkillConfig, SkillItem } from "./skills-model";

const STATUS = { draft: ["Draft", "draft"], published: ["Published", "live"], changed: ["Unpublished changes", "changed"] } as const;

export function SkillEditor({ workspaceId, skill, versions, tools, mcpServers, httpTools, canEdit }: {
  workspaceId: string;
  skill: SkillItem;
  versions: { id: string; number: number; created_at: string }[];
  tools: ToolEntry[];
  mcpServers: McpServerOption[];
  httpTools: HttpTool[];
  canEdit: boolean;
}) {
  const router = useRouter();
  const [name, setName] = useState(skill.name);
  const [description, setDescription] = useState(skill.description);
  const [config, setConfig] = useState<SkillConfig>(skill.config);
  const [revision, setRevision] = useState(skill.revision);
  const [busy, setBusy] = useState(""), [error, setError] = useState("");
  const current = JSON.stringify({ name, description, config });
  const [baseline, setBaseline] = useState(current);
  const dirty = current !== baseline;
  useUnsavedChanges(dirty);
  const [label, tone] = STATUS[dirty && skill.status === "published" ? "changed" : skill.status];

  async function save(): Promise<boolean> {
    setBusy("save");
    setError("");
    try {
      const result = await api<SkillItem>(`/workspaces/${workspaceId}/skills/${skill.id}`, {
        method: "PATCH", body: JSON.stringify({ name, description, config, expected_revision: revision }),
      });
      setRevision(result.revision);
      setBaseline(JSON.stringify({ name: result.name, description: result.description, config: result.config }));
      router.refresh();
      return true;
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not save the skill.");
      return false;
    } finally {
      setBusy("");
    }
  }

  async function publish() {
    if (dirty && !(await save())) return;
    setBusy("publish");
    setError("");
    try {
      await api(`/workspaces/${workspaceId}/skills/${skill.id}/publish`, { method: "POST", body: JSON.stringify({ expected_revision: dirty ? revision + 1 : revision }) });
      router.refresh();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not publish the skill.");
    } finally {
      setBusy("");
    }
  }

  async function archive() {
    if (!window.confirm(`Archive ${skill.name}? Agents that already pinned it keep working; it can't be attached again.`)) return;
    await api(`/workspaces/${workspaceId}/skills/${skill.id}/archive`, { method: "POST" });
    router.push(`/w/${workspaceId}/agents/skills`);
  }

  const setExample = (index: number, key: "input" | "output", value: string) =>
    setConfig({ ...config, examples: config.examples.map((item, i) => (i === index ? { ...item, [key]: value } : item)) });

  return (
    <div className="agent-builder">
      <div className="builder-top">
        <Link href={`/w/${workspaceId}/agents/skills`} className="icon-button" aria-label="Back to skills"><ArrowLeft size={19} /></Link>
        <span className="builder-avatar" aria-hidden="true">📘</span>
        <div className="builder-identity">
          <input className="builder-name" aria-label="Skill name" value={name} maxLength={100} disabled={!canEdit} onChange={(event) => setName(event.target.value)} />
          <span className="row">
            <span className={`builder-status ${tone}`}>{label}{skill.latest ? ` · v${skill.latest.number}` : ""}</span>
            <small className="muted">{dirty ? "Unsaved changes" : `Saved · revision ${revision}`}</small>
          </span>
        </div>
        <div className="row builder-actions">
          {canEdit && <Button variant="ghost" onClick={archive} title="Archive"><Archive size={15} /></Button>}
          <Button variant="outline" onClick={publish} disabled={!canEdit || !!busy || !config.instructions.trim()} title="Freeze this skill so agents can pin it">
            {busy === "publish" ? <LoaderCircle size={15} className="spin" /> : <Rocket size={15} />} Publish
          </Button>
          <Button onClick={save} disabled={!canEdit || !!busy || !dirty || !name.trim()}>
            {busy === "save" ? <LoaderCircle size={15} className="spin" /> : dirty ? <Save size={15} /> : <Check size={15} />} {dirty ? "Save" : "Saved"}
          </Button>
        </div>
      </div>
      {error && <ErrorNotice message={error} />}
      <div className="builder-split">
        <div className="builder-blocks">
          <section className="builder-block open">
            <div className="builder-block-body skill-body">
              <label className="builder-field">
                When should an agent use it?
                <input value={description} maxLength={300} disabled={!canEdit} placeholder="Use when a customer asks about returns or refunds." onChange={(event) => setDescription(event.target.value)} />
                <small className="builder-hint">Agents see only this line until they load the skill, so make it a clear trigger.</small>
              </label>
              <label className="builder-field">
                Instructions
                <textarea className="builder-instructions" rows={12} maxLength={8000} disabled={!canEdit} value={config.instructions} placeholder={"Steps, rules or knowledge the agent should follow.\n- Keep it focused on one job.\n- Write it like a checklist."} onChange={(event) => setConfig({ ...config, instructions: event.target.value })} />
                <small className="builder-hint">{config.instructions.length.toLocaleString()} / 8,000 characters</small>
              </label>
            </div>
          </section>
          <section className="builder-block open">
            <div className="builder-block-body skill-body">
              <div className="builder-row">
                <strong>Examples</strong>
                <Button size="sm" variant="outline" disabled={!canEdit || config.examples.length >= 5} onClick={() => setConfig({ ...config, examples: [...config.examples, { input: "", output: "" }] })}><Plus size={13} /> Add example</Button>
              </div>
              {!config.examples.length && <p className="builder-hint">Optional. One or two good examples teach the style faster than more rules.</p>}
              {config.examples.map((example, index) => (
                <div key={index} className="skill-example">
                  <label className="builder-field">When asked<textarea rows={2} disabled={!canEdit} value={example.input} onChange={(event) => setExample(index, "input", event.target.value)} /></label>
                  <label className="builder-field">A great answer<textarea rows={2} disabled={!canEdit} value={example.output} onChange={(event) => setExample(index, "output", event.target.value)} /></label>
                  <button type="button" className="icon-button" aria-label={`Remove example ${index + 1}`} disabled={!canEdit} onClick={() => setConfig({ ...config, examples: config.examples.filter((_, i) => i !== index) })}><Trash2 size={14} /></button>
                </div>
              ))}
            </div>
          </section>
          <section className="builder-block open">
            <div className="builder-block-body skill-body">
              <strong>Tools this skill needs</strong>
              <p className="builder-hint">Attaching the skill grants these tools to the agent. Workspace approvals and connection checks still apply when the agent is published.</p>
              <ToolShelf
                grants={{ tool_keys: config.tool_keys as AgentConfig["tool_keys"], mcp_tools: config.mcp_tools as AgentConfig["mcp_tools"], http_tools: config.http_tools as AgentConfig["http_tools"] }}
                setGrants={(grants) => setConfig({ ...config, ...grants })}
                supported
                tools={tools}
                mcpServers={mcpServers}
                httpTools={httpTools}
                canEdit={canEdit}
                workspaceId={workspaceId}
              />
            </div>
          </section>
        </div>
        <aside className="builder-try skill-side">
          <div className="try-panel">
            <header><div><strong>How the model sees it</strong><small>Always visible: one line. Loaded on demand: the full skill.</small></div></header>
            <div className="try-log skill-preview">
              <div>
                <span className="skill-preview-label">In every request</span>
                <pre>{`- ${name || "Skill name"}: ${description || "When to use it"}`}</pre>
              </div>
              <div>
                <span className="skill-preview-label">After use_skill(&quot;{name}&quot;)</span>
                <pre>{config.instructions || "Instructions appear here."}{config.examples.map((example) => `\n\nExample input: ${example.input}\nExample output: ${example.output}`).join("")}</pre>
              </div>
              <div>
                <span className="skill-preview-label">Used by</span>
                <p>{skill.used_by.length ? skill.used_by.join(", ") : "No agents yet. Attach it from an agent's Skills block."}</p>
              </div>
              <div>
                <span className="skill-preview-label">Versions</span>
                {versions.length ? (
                  <ul className="skill-versions">{versions.map((version) => <li key={version.id}>v{version.number} · <LocalTime value={version.created_at} /></li>)}</ul>
                ) : <p>Not published yet. Publish so agents can pin it.</p>}
              </div>
            </div>
          </div>
        </aside>
      </div>
    </div>
  );
}
