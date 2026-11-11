"use client";
import { useState, type ReactNode } from "react";
import Link from "next/link";
import { Check, ChevronDown, LoaderCircle, Plus, Search, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ErrorNotice } from "@/components/shared/ui";
import { LocalTime } from "@/components/shared/local-time";
import { api } from "@/lib/api/client";
import type { AgentConfig, Connection } from "@/lib/api/types";
import { SchemaEditor } from "./schema-editor";
import { readFields } from "./schema-fields";
import { newerSkillVersion, type SkillItem } from "./skills-model";
import { IO_PRESETS, SNIPPETS, TONES, hasLine, presetOf, runsPerDollar, toggleLine, toolCount, type BlockId } from "./builder-model";

export function Block({ id, icon, title, summary, done, optional, open, onToggle, children }: {
  id: string; icon: ReactNode; title: string; summary: string; done: boolean; optional?: boolean;
  open: boolean; onToggle: () => void; children: ReactNode;
}) {
  return (
    <section className={`builder-block ${open ? "open" : ""}`} id={`block-${id}`}>
      <button type="button" className="builder-block-head" aria-expanded={open} onClick={onToggle}>
        <span className={`builder-block-icon ${done ? "done" : optional ? "optional" : "todo"}`}>{done ? <Check size={16} /> : icon}</span>
        <span className="builder-block-title">
          <strong>{title}</strong>
          <small>{summary}</small>
        </span>
        <ChevronDown size={16} className={open ? "rotated" : ""} />
      </button>
      {open && <div className="builder-block-body">{children}</div>}
    </section>
  );
}

const METER: { id: BlockId; label: string }[] = [
  { id: "persona", label: "Persona" }, { id: "brain", label: "Brain" }, { id: "tools", label: "Tools" },
  { id: "memory", label: "Memory" }, { id: "io", label: "Input & output" }, { id: "guardrails", label: "Guardrails" },
];

export function ReadinessMeter({ ready, onOpen }: { ready: Record<BlockId, boolean>; onOpen: (id: BlockId) => void }) {
  const done = METER.filter((item) => ready[item.id]).length;
  return (
    <div className="builder-meter" aria-label={`${done} of ${METER.length} parts ready`}>
      <div className="builder-meter-head">
        <strong>{done === METER.length ? "Ready to try and publish ✨" : `${done} of ${METER.length} ready`}</strong>
        <small>{done === METER.length ? "Every part checks out in the editor." : "Click a part to finish it."}</small>
      </div>
      <div className="builder-meter-bar">
        {METER.map((item) => (
          <button key={item.id} type="button" className={ready[item.id] ? "done" : ""} title={`${item.label}: ${ready[item.id] ? "ready" : "needs attention"}`} onClick={() => onOpen(item.id)}>
            <span className="sr-only">{item.label}</span>
          </button>
        ))}
      </div>
    </div>
  );
}

export function Switch({ checked, onChange, label, disabled }: { checked: boolean; onChange: (value: boolean) => void; label: string; disabled?: boolean }) {
  return (
    <button type="button" role="switch" aria-checked={checked} aria-label={label} disabled={disabled} className={`builder-switch ${checked ? "on" : ""}`} onClick={() => onChange(!checked)}>
      <span />
    </button>
  );
}

export function PersonaBlock({ config, setConfig, description, setDescription, canEdit }: {
  config: AgentConfig; setConfig: (config: AgentConfig) => void; description: string; setDescription: (value: string) => void; canEdit: boolean;
}) {
  const instructions = config.instructions;
  return (
    <>
      <label className="builder-field">
        What is this agent for?
        <input value={description} maxLength={500} disabled={!canEdit} placeholder="Answers customer questions about orders" onChange={(event) => setDescription(event.target.value)} />
      </label>
      <div className="builder-field">
        <span>Tone</span>
        <div className="builder-chips">
          {TONES.map((tone) => (
            <button key={tone.id} type="button" disabled={!canEdit} aria-pressed={hasLine(instructions, tone.snippet)} className={`builder-chip ${hasLine(instructions, tone.snippet) ? "on" : ""}`} onClick={() => setConfig({ ...config, instructions: toggleLine(instructions, tone.snippet) })}>
              {tone.label}
            </button>
          ))}
        </div>
      </div>
      <label className="builder-field">
        Instructions
        <textarea
          className="builder-instructions"
          rows={9}
          maxLength={32000}
          disabled={!canEdit}
          value={instructions}
          placeholder={"You help customers with their orders.\nLook up the order before answering.\nIf you can't find it, ask for the order number."}
          onChange={(event) => setConfig({ ...config, instructions: event.target.value })}
        />
      </label>
      <div className="builder-chips">
        {SNIPPETS.map((snippet) => (
          <button key={snippet.label} type="button" disabled={!canEdit} className={`builder-chip ghost ${hasLine(instructions, snippet.text) ? "on" : ""}`} onClick={() => setConfig({ ...config, instructions: toggleLine(instructions, snippet.text) })}>
            {hasLine(instructions, snippet.text) ? <Check size={12} /> : <Plus size={12} />} {snippet.label}
          </button>
        ))}
      </div>
      <p className="builder-hint">{instructions.length.toLocaleString()} / 32,000 characters · Instructions guide behaviour; tool switches decide what it can reach.</p>
    </>
  );
}

const PROVIDERS: { id: AgentConfig["provider"]; label: string; emoji: string }[] = [
  { id: "openai", label: "OpenAI", emoji: "🟢" },
  { id: "anthropic", label: "Claude", emoji: "🟠" },
  { id: "gemini", label: "Gemini", emoji: "🔷" },
  { id: "openrouter", label: "OpenRouter", emoji: "🔀" },
  { id: "deepseek", label: "DeepSeek", emoji: "🐋" },
];

export function BrainBlock({ config, setConfig, connections, workspaceId, canEdit }: {
  config: AgentConfig; setConfig: (config: AgentConfig) => void; connections: Connection[]; workspaceId: string; canEdit: boolean;
}) {
  const connection = connections.find((item) => item.provider === config.provider);
  function chooseModel(modelId: string, provider = config.provider) {
    const tools = connections.find((item) => item.provider === provider)?.model_capabilities[modelId]?.local_tools;
    // Tool grants only work on models that support tools; drop them rather than keep dead grants.
    setConfig({ ...config, provider, model_id: modelId, ...(tools ? {} : { tool_keys: [], mcp_tools: [], http_tools: [], workflow_tools: [] }) });
  }
  return (
    <>
      <div className="builder-provider-grid">
        {PROVIDERS.map((provider) => {
          const linked = connections.find((item) => item.provider === provider.id && item.state === "active");
          return (
            <button
              key={provider.id}
              type="button"
              disabled={!canEdit || !linked}
              className={`builder-provider ${config.provider === provider.id ? "selected" : ""} ${linked ? "" : "missing"}`}
              onClick={() => linked && chooseModel(linked.default_model_id || "", provider.id)}
            >
              <span aria-hidden="true">{provider.emoji}</span>
              <strong>{provider.label}</strong>
              <small>{linked ? "Connected" : "Not connected"}</small>
            </button>
          );
        })}
      </div>
      {connection?.state === "active" ? (
        <div className="builder-model-list" role="radiogroup" aria-label="Model">
          {connection.verified_models.map((id) => {
            const capability = connection.model_capabilities[id];
            return (
              <button key={id} type="button" role="radio" aria-checked={config.model_id === id} disabled={!canEdit} className={`builder-model ${config.model_id === id ? "selected" : ""}`} onClick={() => chooseModel(id)}>
                <strong>{id}</strong>
                <span className="builder-model-badges">
                  <em className={capability?.runnable ? "good" : ""}>{capability?.runnable ? "Live runs" : "Setup only"}</em>
                  {capability?.local_tools && <em className="good">Tools</em>}
                  {capability?.input_usd_per_million && <em>${capability.input_usd_per_million} / ${capability.output_usd_per_million} per M tokens</em>}
                </span>
              </button>
            );
          })}
        </div>
      ) : (
        <p className="builder-hint">
          {PROVIDERS.find((item) => item.id === config.provider)?.label} isn&apos;t connected yet.{" "}
          <Link className="text-link" href={`/w/${workspaceId}/integrations`}>Connect a provider</Link> to choose a model.
        </p>
      )}
    </>
  );
}

export function MemoryBlock({ config, setConfig, inputText, agentId, workspaceId, canEdit, canManage }: {
  config: AgentConfig; setConfig: (config: AgentConfig) => void; inputText: string; agentId?: string; workspaceId: string; canEdit: boolean; canManage: boolean;
}) {
  const memory = config.memory;
  const fields = readFields(inputText)?.filter((field) => field.type === "string" || field.type === "integer") ?? [];
  return (
    <>
      <div className="builder-row">
        <div>
          <strong>Remember conversations</strong>
          <p className="builder-hint">Earlier messages of the same conversation are sent along, encrypted at rest.</p>
        </div>
        <Switch
          label="Remember conversations"
          checked={!!memory}
          disabled={!canEdit}
          onChange={(on) => setConfig({ ...config, memory: on ? { key_pointer: "/conversation_id", max_turns: 10, retention_days: 30 } : null })}
        />
      </div>
      {memory && (
        <>
          <label className="builder-field">
            Conversation ID field
            <input value={memory.key_pointer} disabled={!canEdit} spellCheck={false} onChange={(event) => setConfig({ ...config, memory: { ...memory, key_pointer: event.target.value } })} />
          </label>
          {fields.length > 0 && (
            <div className="builder-chips">
              {fields.map((field) => (
                <button key={field.name} type="button" disabled={!canEdit} className={`builder-chip ghost ${memory.key_pointer === `/${field.name}` ? "on" : ""}`} onClick={() => setConfig({ ...config, memory: { ...memory, key_pointer: `/${field.name}` } })}>
                  /{field.name}
                </button>
              ))}
            </div>
          )}
          <Slider label="Exchanges to remember" value={memory.max_turns} min={1} max={20} disabled={!canEdit} display={`${memory.max_turns}`} onChange={(max_turns) => setConfig({ ...config, memory: { ...memory, max_turns } })} />
          <Slider label="Forget after" value={memory.retention_days} min={1} max={90} disabled={!canEdit} display={`${memory.retention_days} days`} onChange={(retention_days) => setConfig({ ...config, memory: { ...memory, retention_days } })} />
          {agentId && canManage && <MemoryInspector workspaceId={workspaceId} agentId={agentId} />}
        </>
      )}
    </>
  );
}

function MemoryInspector({ workspaceId, agentId }: { workspaceId: string; agentId: string }) {
  const base = `/workspaces/${workspaceId}/agents/${agentId}/memory`;
  const [conversation, setConversation] = useState("");
  const [result, setResult] = useState<{ conversations: number; turns: { role: string; content: unknown; created_at: string }[] } | null>(null);
  const [busy, setBusy] = useState(false), [error, setError] = useState("");
  async function look(id = conversation) {
    setBusy(true);
    setError("");
    try {
      setResult(await api(`${base}${id ? `?conversation_id=${encodeURIComponent(id)}` : ""}`));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not read memory.");
    } finally {
      setBusy(false);
    }
  }
  async function forget(all: boolean) {
    if (!window.confirm(all ? "Forget every conversation this agent remembers?" : "Forget this conversation?")) return;
    setBusy(true);
    try {
      await api(`${base}${all ? "" : `?conversation_id=${encodeURIComponent(conversation)}`}`, { method: "DELETE" });
      await look(all ? "" : conversation);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not forget.");
      setBusy(false);
    }
  }
  return (
    <details className="builder-inspector" onToggle={(event) => (event.currentTarget.open && !result ? look("") : undefined)}>
      <summary>Memory inspector</summary>
      <p className="builder-hint">{result ? `${result.conversations} conversation${result.conversations === 1 ? "" : "s"} remembered.` : "Loading…"} Only a hash of each conversation ID is stored, so look one up by its ID.</p>
      <div className="builder-row">
        <input aria-label="Conversation ID" placeholder="conversation ID" value={conversation} onChange={(event) => setConversation(event.target.value)} />
        <Button size="sm" variant="outline" disabled={busy || !conversation} onClick={() => look()}>{busy ? <LoaderCircle size={13} className="spin" /> : <Search size={13} />}Look up</Button>
      </div>
      {result?.turns.length ? (
        <>
          <ol className="builder-turns">
            {result.turns.map((turn, index) => (
              <li key={index} className={turn.role}>
                <small>{turn.role} · <LocalTime value={turn.created_at} /></small>
                <pre>{JSON.stringify(turn.content, null, 2)}</pre>
              </li>
            ))}
          </ol>
          <Button size="sm" variant="outline" disabled={busy} onClick={() => forget(false)}><Trash2 size={13} />Forget this conversation</Button>
        </>
      ) : result && conversation ? <p className="builder-hint">Nothing remembered for that ID.</p> : null}
      {!!result?.conversations && <button type="button" className="text-link builder-danger-link" disabled={busy} onClick={() => forget(true)}>Forget all conversations</button>}
      {error && <ErrorNotice message={error} />}
    </details>
  );
}

export function IoBlock({ input, output, setInput, setOutput, strictOutput, canEdit }: {
  input: string; output: string; setInput: (text: string) => void; setOutput: (text: string) => void; strictOutput: boolean; canEdit: boolean;
}) {
  const preset = presetOf(input, output);
  const [custom, setCustom] = useState(preset === "custom");
  return (
    <>
      <div className="builder-preset-grid">
        {IO_PRESETS.map((item) => (
          <button key={item.id} type="button" disabled={!canEdit} className={`builder-preset ${preset === item.id ? "selected" : ""}`} onClick={() => { setInput(JSON.stringify(item.input, null, 2)); setOutput(JSON.stringify(item.output, null, 2)); setCustom(false); }}>
            <span aria-hidden="true">{item.emoji}</span>
            <strong>{item.label}</strong>
            <small>{item.description}</small>
          </button>
        ))}
        <button type="button" disabled={!canEdit} className={`builder-preset ${preset === "custom" ? "selected" : ""}`} onClick={() => setCustom(true)}>
          <span aria-hidden="true">🧩</span>
          <strong>Custom</strong>
          <small>Design your own fields.</small>
        </button>
      </div>
      {(custom || preset === "custom") && (
        <div className="builder-schemas">
          <SchemaEditor title="What it receives" value={input} onChange={setInput} disabled={!canEdit} strict={false} />
          <SchemaEditor title="What it returns" value={output} onChange={setOutput} disabled={!canEdit} strict={strictOutput} />
        </div>
      )}
    </>
  );
}

function Slider({ label, value, min, max, step = 1, display, onChange, disabled }: {
  label: string; value: number; min: number; max: number; step?: number; display: string; onChange: (value: number) => void; disabled?: boolean;
}) {
  return (
    <label className="builder-slider">
      <span>{label}<strong>{display}</strong></span>
      <input type="range" min={min} max={max} step={step} value={value} disabled={disabled} onChange={(event) => onChange(Number(event.target.value))} />
    </label>
  );
}

export function GuardrailsBlock({ config, setConfig, connection, canEdit }: {
  config: AgentConfig; setConfig: (config: AgentConfig) => void; connection: Connection | undefined; canEdit: boolean;
}) {
  const limits = config.limits;
  const set = (key: keyof AgentConfig["limits"], value: number | string) => setConfig({ ...config, limits: { ...limits, [key]: value } });
  const perDollar = runsPerDollar(connection?.model_capabilities[config.model_id], toolCount(config) > 0);
  const budget = Number(limits.max_cost_usd);
  return (
    <>
      <div className="builder-estimate" aria-live="polite">
        {perDollar ? (
          <>💡 About <strong>{perDollar.toLocaleString()} runs per $1</strong> for a typical message on {config.model_id}. Each run stops at ${budget.toFixed(2)}.</>
        ) : (
          <>Each run stops at <strong>${budget.toFixed(2)}</strong>. Choose a model with published prices to see a run estimate.</>
        )}
      </div>
      <Slider label="Budget per run" value={budget} min={0.01} max={2} step={0.01} display={`$${budget.toFixed(2)}`} disabled={!canEdit} onChange={(value) => set("max_cost_usd", value.toFixed(2))} />
      <Slider label="Tool calls per run" value={limits.max_tool_calls} min={0} max={32} display={`${limits.max_tool_calls}`} disabled={!canEdit} onChange={(value) => set("max_tool_calls", value)} />
      <Slider label="Model turns per run" value={limits.max_iterations} min={1} max={20} display={`${limits.max_iterations}`} disabled={!canEdit} onChange={(value) => set("max_iterations", value)} />
      <Slider label="Time limit" value={limits.timeout_seconds} min={5} max={300} step={5} display={`${limits.timeout_seconds}s`} disabled={!canEdit} onChange={(value) => set("timeout_seconds", value)} />
      <Slider label="Longest answer" value={limits.max_output_tokens} min={256} max={4096} step={64} display={`${limits.max_output_tokens} tokens`} disabled={!canEdit} onChange={(value) => set("max_output_tokens", value)} />
    </>
  );
}

export function SkillsBlock({ config, setConfig, skills, pinned, onDemand, workspaceId, canEdit }: {
  config: AgentConfig;
  setConfig: (config: AgentConfig) => void;
  skills: SkillItem[];
  /** Skills frozen in the live published version, to spot newer skill versions. */
  pinned: AgentConfig["skills"] | undefined;
  /** Null while the model is unknown, for example before its provider is connected. */
  onDemand: boolean | null;
  workspaceId: string;
  canEdit: boolean;
}) {
  const attached = new Set(config.skills.map((grant) => grant.skill_id));
  const missing = config.skills.filter((grant) => !skills.some((skill) => skill.id === grant.skill_id));
  const toggle = (skill: SkillItem, on: boolean) =>
    setConfig({
      ...config,
      skills: on ? [...config.skills, { skill_id: skill.id, name: skill.name, description: skill.description, examples: [], instructions: "" }] : config.skills.filter((grant) => grant.skill_id !== skill.id),
    });
  return (
    <>
      <p className="builder-hint">
        {onDemand === null
          ? "Models that can call tools load a skill only when a request needs it; others get attached skills in full."
          : onDemand
            ? "The agent sees each skill's one-line trigger and loads the full skill only when a request needs it."
            : "This model can't call tools, so attached skills are added to every request in full."}
      </p>
      {skills.length ? (
        <div className="tool-switches">
          {skills.map((skill) => {
            const newer = newerSkillVersion(pinned, skill);
            return (
              <div key={skill.id} className={`tool-row ${attached.has(skill.id) ? "on" : ""}`}>
                <span className="skill-row-emoji" aria-hidden="true">📘</span>
                <span className="tool-row-main">
                  <strong>{skill.name} {skill.latest && <em className="skill-version">v{skill.latest.number}</em>}</strong>
                  <small>{skill.description || "No trigger description yet"}</small>
                  {!skill.latest && <small className="warn-text">Draft only: publish the skill before publishing this agent.</small>}
                  {newer && <small className="warn-text">v{newer} is out. Republish this agent to use it.</small>}
                </span>
                <Switch label={`Attach ${skill.name}`} checked={attached.has(skill.id)} disabled={!canEdit || (!attached.has(skill.id) && config.skills.length >= 8)} onChange={(on) => toggle(skill, on)} />
              </div>
            );
          })}
        </div>
      ) : (
        <p className="builder-hint">No skills yet. Starters like “Refund & returns policy” or “Brand voice” take one click.</p>
      )}
      {missing.map((grant) => (
        <p key={grant.skill_id} className="builder-hint warn">
          {grant.name || "A skill"} was archived or removed.{" "}
          <button type="button" className="text-link" disabled={!canEdit} onClick={() => setConfig({ ...config, skills: config.skills.filter((item) => item !== grant) })}>Detach it</button>
        </p>
      ))}
      <Link className="text-link" href={`/w/${workspaceId}/agents/skills`}>Browse and edit skills</Link>
    </>
  );
}
