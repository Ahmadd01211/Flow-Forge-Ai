"use client";
import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  ArrowLeft,
  Bot,
  Check,
  Code2,
  FileText,
  Gauge,
  LoaderCircle,
  Save,
  ShieldCheck,
  Sparkles,
  History,
  FlaskConical,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge, ErrorNotice } from "@/components/shared/ui";
import { api } from "@/lib/api/client";
import { useUnsavedChanges } from "@/lib/use-unsaved-changes";
import type {
  Agent,
  AgentConfig,
  AgentVersion,
  Connection,
  VersionList,
} from "@/lib/api/types";
import { VersionHistory } from "./version-history";
import type { ToolEntry } from "@/features/tools/tool-registry";
import { isRunnableModel } from "./runnable-models";
import { agentStarters } from "./agent-starters";
import { SchemaEditor } from "./schema-editor";
import type { components } from "@/lib/api/generated";

const defaultConfig: AgentConfig = {
  schema_version: 1,
  instructions: "",
  provider: "openai",
  model_id: "",
  tool_keys: [],
  input_schema: {
    type: "object",
    properties: { ticket: { type: "string" } },
    required: ["ticket"],
    additionalProperties: false,
  },
  output_schema: {
    type: "object",
    properties: { priority: { type: "string", enum: ["urgent", "normal"] } },
    required: ["priority"],
    additionalProperties: false,
  },
  limits: {
    max_iterations: 8,
    timeout_seconds: 60,
    max_cost_usd: "0.10",
    max_tool_calls: 8,
    max_output_tokens: 4096,
  },
};
const tabs = [
  { id: "instructions", label: "Instructions", icon: FileText },
  { id: "model", label: "Model & tools", icon: Sparkles },
  { id: "schemas", label: "Schemas", icon: Code2 },
  { id: "limits", label: "Limits", icon: Gauge },
  { id: "versions", label: "History", icon: History },
];
export function AgentEditor({
  agent,
  workspaceId,
  versions,
  initialTab = "instructions",
  canEdit = true,
  connections = [],
  tools = [],
}: {
  agent?: Agent;
  workspaceId: string;
  versions?: VersionList;
  initialTab?: string;
  canEdit?: boolean;
  connections?: Connection[];
  tools?: ToolEntry[];
}) {
  const preferredConnection = connections.find(
    (item) => item.state === "active" && item.default_model_id,
  );
  const router = useRouter(),
    [name, setName] = useState(agent?.name || ""),
    [description, setDescription] = useState(agent?.description || ""),
    [config, setConfig] = useState<AgentConfig>(
      agent?.config ||
        (preferredConnection
          ? {
              ...defaultConfig,
              provider: preferredConnection.provider,
              model_id: preferredConnection.default_model_id || "",
            }
          : defaultConfig),
    ),
    [tab, setTab] = useState(initialTab),
    [revision, setRevision] = useState(agent?.revision || 1),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [saved, setSaved] = useState(false),
    [snapshotBusy, setSnapshotBusy] = useState(false),
    [publishBusy, setPublishBusy] = useState(false),
    [summary, setSummary] = useState("");
  const connection = connections.find(
    (item) => item.provider === config.provider,
  );
  const [input, setInput] = useState(
      JSON.stringify(config.input_schema, null, 2),
    ),
    [output, setOutput] = useState(
      JSON.stringify(config.output_schema, null, 2),
    );
  const current = JSON.stringify({ name, description, config, input, output });
  const [readiness, setReadiness] = useState<
    components["schemas"]["ReadinessRead"] | null
  >(null);
  const [checking, setChecking] = useState(false);
  const [baseline, setBaseline] = useState(current);
  useUnsavedChanges(current !== baseline);
  async function checkReadiness() {
    if (!agent || current !== baseline) return;
    setChecking(true);
    setError("");
    try {
      setReadiness(
        await api(`/workspaces/${workspaceId}/agents/${agent.id}/readiness`),
      );
    } catch (cause) {
      setError(
        cause instanceof Error
          ? cause.message
          : "Could not check publication readiness.",
      );
    } finally {
      setChecking(false);
    }
  }
  function applyStarter(starter: (typeof agentStarters)[number]) {
    setName(starter.name);
    setDescription(starter.description);
    setConfig((previous) => ({
      ...previous,
      instructions: starter.instructions,
      input_schema: starter.inputSchema,
      output_schema: starter.outputSchema,
    }));
    setInput(JSON.stringify(starter.inputSchema, null, 2));
    setOutput(JSON.stringify(starter.outputSchema, null, 2));
    setTab("instructions");
    setSaved(false);
  }
  async function createSnapshot() {
    if (!agent || current !== baseline) return;
    setSnapshotBusy(true);
    setError("");
    try {
      await api<AgentVersion>(
        `/workspaces/${workspaceId}/agents/${agent.id}/test-snapshots`,
        {
          method: "POST",
          body: JSON.stringify({
            expected_revision: revision,
            change_summary: summary,
          }),
        },
      );
      setTab("versions");
      setSummary("");
      router.refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Snapshot creation failed.");
    } finally {
      setSnapshotBusy(false);
    }
  }
  async function publish() {
    if (!agent || current !== baseline) return;
    setPublishBusy(true);
    setError("");
    try {
      await api<AgentVersion>(
        `/workspaces/${workspaceId}/agents/${agent.id}/versions`,
        {
          method: "POST",
          body: JSON.stringify({
            expected_revision: revision,
            change_summary: summary,
          }),
        },
      );
      setTab("versions");
      setSummary("");
      router.refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Publication failed.");
    } finally {
      setPublishBusy(false);
    }
  }
  function limit(key: keyof AgentConfig["limits"], value: string) {
    setConfig({
      ...config,
      limits: {
        ...config.limits,
        [key]: key === "max_cost_usd" ? value : Number(value),
      },
    });
    setSaved(false);
  }
  async function save() {
    setBusy(true);
    setError("");
    try {
      const updated = {
        ...config,
        input_schema: JSON.parse(input),
        output_schema: JSON.parse(output),
      };
      const result = await api<Agent>(
        `/workspaces/${workspaceId}/agents${agent ? `/${agent.id}` : ""}`,
        {
          method: agent ? "PATCH" : "POST",
          body: JSON.stringify({
            name,
            description,
            config: updated,
            ...(agent ? { expected_revision: revision } : {}),
          }),
        },
      );
      setConfig(result.config);
      setRevision(result.revision);
      setSaved(true);
      setReadiness(null);
      setBaseline(
        JSON.stringify({
          name,
          description,
          config: result.config,
          input,
          output,
        }),
      );
      if (!agent) router.replace(`/w/${workspaceId}/agents/${result.id}`);
      else router.refresh();
    } catch (e) {
      setError(
        e instanceof SyntaxError
          ? "Input and output schemas must contain valid JSON."
          : e instanceof Error
            ? e.message
            : "Could not save this agent.",
      );
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      {!agent && (
        <section className="agent-starters" aria-label="Agent quick starts">
          <div>
            <strong>Start with a working shape</strong>
            <p>
              Choose a starting configuration, then edit every instruction and
              field.
            </p>
          </div>
          <div className="agent-starter-options">
            {agentStarters.map((starter) => (
              <button
                key={starter.id}
                type="button"
                onClick={() => applyStarter(starter)}
                disabled={!canEdit}
              >
                <Bot size={17} />
                <span>
                  <strong>{starter.name}</strong>
                  <small>{starter.description}</small>
                </span>
                <ArrowLeft size={14} className="starter-arrow" />
              </button>
            ))}
          </div>
        </section>
      )}
      <div className="editor-heading">
        <div className="row">
          <Link
            href={`/w/${workspaceId}/agents`}
            className="icon-button"
            aria-label="Back to agents"
          >
            <ArrowLeft size={19} />
          </Link>
          <div>
            <div className="row">
              <h1>{agent ? "Agent configuration" : "Create an agent"}</h1>
              <Badge>Draft · r{revision}</Badge>
            </div>
            <p>Define a clear purpose. Give it clear boundaries.</p>
          </div>
        </div>
        <div className="row agent-editor-actions">
          <Button
            variant="outline"
            onClick={publish}
            disabled={
              !agent ||
              busy ||
              snapshotBusy ||
              publishBusy ||
              current !== baseline ||
              !config.instructions.trim() ||
              !connection?.verified_models.includes(config.model_id) ||
              connection?.state !== "active" ||
              !canEdit
            }
            title="Freeze a publishable definition after provider and schema checks. Supported models can then be run from History."
          >
            {publishBusy ? (
              <LoaderCircle size={15} className="spin" />
            ) : (
              <ShieldCheck size={15} />
            )}
            Publish version
          </Button>
          <Button
            variant="outline"
            onClick={createSnapshot}
            disabled={
              !agent ||
              busy ||
              snapshotBusy ||
              publishBusy ||
              current !== baseline ||
              !config.instructions.trim() ||
              !canEdit
            }
            title={
              current !== baseline
                ? "Save your changes before creating a snapshot."
                : !agent
                  ? "Save the agent first."
                  : "Freeze the saved configuration without a model call."
            }
          >
            {snapshotBusy ? (
              <LoaderCircle size={15} className="spin" />
            ) : (
              <FlaskConical size={15} />
            )}
            Create snapshot
          </Button>
          <Button onClick={save} disabled={busy || !name.trim() || !canEdit}>
            {busy ? (
              <LoaderCircle size={16} className="spin" />
            ) : saved && current === baseline ? (
              <Check size={16} />
            ) : (
              <Save size={16} />
            )}{" "}
            {saved && current === baseline ? "Saved" : "Save draft"}
          </Button>
        </div>
      </div>
      {error && <ErrorNotice message={error} />}
      <div className="agent-editor-grid">
        <div>
          <section className="panel form-panel">
            <div className="section-number">
              01 <span>Agent identity</span>
            </div>
            <div className="form-stack">
              <label>
                Agent name
                <input
                  placeholder="e.g. Support triage agent"
                  disabled={!canEdit}
                  maxLength={100}
                  value={name}
                  onChange={(e) => {
                    setName(e.target.value);
                    setSaved(false);
                  }}
                />
              </label>
              {agent && (
                <label>
                  Snapshot change summary{" "}
                  <span className="field-hint">
                    Optional. Stored only when a new snapshot is created.
                  </span>
                  <input
                    value={summary}
                    disabled={!canEdit}
                    onChange={(e) => setSummary(e.target.value)}
                    maxLength={1000}
                    placeholder="e.g. Clarified urgent ticket criteria"
                  />
                </label>
              )}
              <label>
                Description
                <textarea
                  rows={2}
                  maxLength={500}
                  placeholder="What does this agent help your team accomplish?"
                  disabled={!canEdit}
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                />
              </label>
            </div>
          </section>
          <section className="panel">
            <div
              className="editor-tabs"
              role="tablist"
              aria-label="Agent configuration"
            >
              {tabs.map((t) => (
                <button
                  role="tab"
                  aria-selected={tab === t.id}
                  key={t.id}
                  onClick={() => setTab(t.id)}
                  className={tab === t.id ? "active" : ""}
                >
                  <t.icon size={15} />
                  {t.label}
                </button>
              ))}
            </div>
            <div className="tab-content" role="tabpanel">
              {tab === "versions" ? (
                agent && versions ? (
                  <VersionHistory
                    key={`${agent.id}-${versions.items[0]?.id || "empty"}`}
                    agent={{ ...agent, revision }}
                    initial={versions}
                    dirty={current !== baseline}
                    canEdit={canEdit}
                    connections={connections}
                  />
                ) : (
                  <div className="inline-empty">
                    <History size={25} />
                    <h3>Save your agent first</h3>
                    <p>
                      Saved instructions can be frozen as an immutable test
                      snapshot.
                    </p>
                  </div>
                )
              ) : tab === "instructions" ? (
                <>
                  <div className="row between">
                    <div>
                      <h2>Tell your agent how to work</h2>
                      <p className="muted">
                        Be specific about its role, decisions and expected
                        output.
                      </p>
                    </div>
                    <FileText size={19} className="muted" />
                  </div>
                  <label className="form-stack mt-6">
                    Instructions
                    <textarea
                      className="instructions-editor"
                      disabled={!canEdit}
                      placeholder={
                        "You are a support triage agent.\n\nRead the incoming ticket and classify its priority as urgent or normal.\nReturn a structured result matching the output schema.\nDo not take actions outside your approved tools."
                      }
                      value={config.instructions}
                      maxLength={32000}
                      onChange={(e) =>
                        setConfig({ ...config, instructions: e.target.value })
                      }
                      rows={13}
                    />
                  </label>
                  <span className="field-hint">
                    {config.instructions.length.toLocaleString()} / 32,000
                    characters · Instructions guide behavior; tool permissions
                    enforce access.
                  </span>
                </>
              ) : tab === "model" ? (
                <>
                  <h2>Model & approved tools</h2>
                  <p className="muted">
                    Select a model verified for this workspace.
                  </p>
                  <label className="form-stack mt-6">
                    Provider
                    <select
                      value={config.provider}
                      onChange={(e) =>
                        setConfig({
                          ...config,
                          provider: e.target.value as AgentConfig["provider"],
                          tool_keys: [],
                          model_id:
                            connections.find(
                              (item) => item.provider === e.target.value,
                            )?.default_model_id || "",
                        })
                      }
                      disabled={!canEdit}
                    >
                      <option value="openai">OpenAI</option>
                      <option value="openrouter">OpenRouter</option>
                      <option value="anthropic">Claude (Anthropic)</option>
                      <option value="gemini">Gemini (Google)</option>
                      <option value="deepseek">DeepSeek</option>
                    </select>
                  </label>
                  {connection?.state === "active" ? (
                    <div className="form-stack mt-6">
                      <label>
                        Verified model
                        <select
                          value={config.model_id}
                          onChange={(e) =>
                            setConfig({
                              ...config,
                              model_id: e.target.value,
                              tool_keys: connection.model_capabilities[
                                e.target.value
                              ]?.local_tools
                                ? config.tool_keys
                                : [],
                            })
                          }
                          disabled={!canEdit}
                        >
                          <option value="">Choose a model</option>
                          {connection.verified_models.map((id) => (
                            <option value={id} key={id}>
                              {id}
                              {isRunnableModel(connections, config.provider, id)
                                ? " · Live runs"
                                : " · Setup only"}
                            </option>
                          ))}
                        </select>
                      </label>
                      <p className="field-hint">
                        Access was checked on{" "}
                        {new Date(connection.verified_at).toLocaleString()}.
                        Publishing validates your saved schema; it does not
                        execute the model. Live runs are available only for
                        models marked above.
                      </p>
                    </div>
                  ) : (
                    <div className="inline-empty">
                      <Sparkles size={25} />
                      <h3>No model provider connected</h3>
                      <p>
                        Connect a provider in Integrations before choosing a
                        model or publishing.
                      </p>
                      <Button asChild variant="outline">
                        <Link href={`/w/${workspaceId}/integrations`}>
                          Open integrations
                        </Link>
                      </Button>
                    </div>
                  )}
                  <div className="permission-callout">
                    <ShieldCheck size={18} />
                    <div>
                      <strong>
                        {config.tool_keys.length
                          ? `${config.tool_keys.length} tool grant${config.tool_keys.length === 1 ? "" : "s"} selected`
                          : "No tool access granted"}
                      </strong>
                      <p>
                        Models with local tool support can call selected tools
                        after publication. Workspace approval is checked when
                        each run starts and before each call.
                      </p>
                    </div>
                  </div>
                  <div className="agent-tool-list">
                    {tools.map((tool) => (
                      <div key={tool.key} className="agent-tool-option">
                        <label className="agent-tool-selection">
                          <input
                            type="checkbox"
                            aria-label={`Grant ${tool.name}`}
                            checked={config.tool_keys.includes(
                              tool.key as AgentConfig["tool_keys"][number],
                            )}
                            disabled={
                              !canEdit ||
                              !tool.installed ||
                              !connection?.model_capabilities[config.model_id]
                                ?.local_tools
                            }
                            onChange={(event) => {
                              const keys = event.target.checked
                                ? [
                                    ...config.tool_keys,
                                    tool.key as AgentConfig["tool_keys"][number],
                                  ]
                                : config.tool_keys.filter(
                                    (key) => key !== tool.key,
                                  );
                              setConfig({ ...config, tool_keys: keys });
                            }}
                          />
                          <span>
                            <strong>{tool.name}</strong>
                            <small>
                              {tool.installed
                                ? tool.description
                                : "Approve in Tool Registry first"}
                            </small>
                          </span>
                        </label>
                        <details className="agent-tool-contract">
                          <summary>Arguments and permissions</summary>
                          <p>
                            {tool.read_only
                              ? "Read-only local tool. No network or credential access."
                              : "Review this tool's permissions before granting access."}
                          </p>
                          <pre>
                            {JSON.stringify(tool.input_schema, null, 2)}
                          </pre>
                        </details>
                      </div>
                    ))}
                    {!tools.length && (
                      <p className="field-hint">
                        No reviewed tools are available yet.
                      </p>
                    )}
                    <Button asChild variant="outline" size="sm">
                      <Link href={`/w/${workspaceId}/tools`}>
                        Open Tool Registry
                      </Link>
                    </Button>
                  </div>
                </>
              ) : tab === "schemas" ? (
                <>
                  <h2>Make inputs and outputs predictable</h2>
                  <p className="muted">
                    Object schemas describe the data this agent receives and
                    returns.
                  </p>
                  <div className="schema-grid">
                    <SchemaEditor
                      title="Input"
                      value={input}
                      onChange={setInput}
                      disabled={!canEdit}
                      strict={false}
                    />
                    <SchemaEditor
                      title="Output"
                      value={output}
                      onChange={setOutput}
                      disabled={!canEdit}
                      strict={
                        config.provider === "openai" ||
                        config.provider === "openrouter"
                      }
                    />
                  </div>
                </>
              ) : (
                <>
                  <h2>Set the boundaries</h2>
                  <p className="muted">
                    Supported live models use these caps when a run starts.
                  </p>
                  <div className="limits-grid">
                    <label>
                      Maximum output tokens
                      <input
                        type="number"
                        min={16}
                        max={4096}
                        disabled={!canEdit}
                        value={config.limits.max_output_tokens}
                        onChange={(e) =>
                          limit("max_output_tokens", e.target.value)
                        }
                      />
                      <span className="field-hint">
                        16–4,096 per model call; the cost budget may lower this
                        allowance.
                      </span>
                    </label>
                    <label>
                      Maximum iterations
                      <input
                        type="number"
                        min={1}
                        max={20}
                        value={config.limits.max_iterations}
                        disabled={!canEdit}
                        onChange={(e) =>
                          limit("max_iterations", e.target.value)
                        }
                      />
                      <span className="field-hint">
                        At most 20 model calls.
                      </span>
                    </label>
                    <label>
                      Execution timeout (seconds)
                      <input
                        type="number"
                        min={1}
                        max={300}
                        value={config.limits.timeout_seconds}
                        disabled={!canEdit}
                        onChange={(e) =>
                          limit("timeout_seconds", e.target.value)
                        }
                      />
                    </label>
                    <label>
                      Maximum cost per run (USD)
                      <input
                        inputMode="decimal"
                        value={config.limits.max_cost_usd}
                        disabled={!canEdit}
                        onChange={(e) => limit("max_cost_usd", e.target.value)}
                      />
                    </label>
                    <label>
                      Maximum tool calls
                      <input
                        type="number"
                        min={0}
                        max={32}
                        value={config.limits.max_tool_calls}
                        disabled={!canEdit}
                        onChange={(e) =>
                          limit("max_tool_calls", e.target.value)
                        }
                      />
                    </label>
                  </div>
                </>
              )}
            </div>
          </section>
        </div>
        <aside className="agent-summary panel">
          <span className="node-icon purple">
            <Bot size={27} />
          </span>
          <h2>{name || "Your new agent"}</h2>
          <p>{description || "A focused agent starts with a clear purpose."}</p>
          <Badge tone="purple">Draft configuration</Badge>
          <div className="summary-divider" />
          <div className="summary-line">
            <span>Instructions</span>
            <strong>{config.instructions ? "Configured" : "Not set"}</strong>
          </div>
          <div className="summary-line">
            <span>Model provider</span>
            <strong>
              {connection?.state === "active"
                ? `${connection.display_name} · ${config.model_id || "Choose model"}`
                : "Not connected"}
            </strong>
          </div>
          <div className="summary-line">
            <span>Tool permissions</span>
            <strong>
              {config.tool_keys.length
                ? `${config.tool_keys.length} selected`
                : "None"}
            </strong>
          </div>
          <div className="summary-divider" />
          <h3>Resource budget</h3>
          <div className="summary-line">
            <span>Output tokens</span>
            <strong>{config.limits.max_output_tokens} max / call</strong>
          </div>
          <div className="summary-line">
            <span>Iterations</span>
            <strong>{config.limits.max_iterations} max</strong>
          </div>
          <div className="summary-line">
            <span>Timeout</span>
            <strong>{config.limits.timeout_seconds}s</strong>
          </div>
          <div className="summary-line">
            <span>Spend</span>
            <strong>${config.limits.max_cost_usd} / run</strong>
          </div>
          <div className="permission-callout">
            <ShieldCheck size={17} />
            <p>Saving a draft does not publish it or trigger a model call.</p>
          </div>
          <div className="summary-divider" />
          <h3>Publication checklist</h3>
          <p>
            Save your draft, then check schemas, model access, tools and limits.
            This does not call a model.
          </p>
          <Button
            variant="outline"
            disabled={
              !agent ||
              current !== baseline ||
              checking ||
              busy ||
              publishBusy ||
              snapshotBusy
            }
            onClick={checkReadiness}
          >
            {checking ? "Checking…" : "Check readiness"}
          </Button>
          {current !== baseline && (
            <p className="field-hint">Save changes to refresh the checklist.</p>
          )}
          {readiness && current === baseline && (
            <div role="status">
              <p>
                {readiness.publishable
                  ? readiness.runnable
                    ? "Ready to publish and run."
                    : "Ready to publish for setup only."
                  : "Resolve these issues before publishing."}
              </p>
              {[...readiness.errors, ...readiness.warnings].map((issue, i) => (
                <div className="readiness-issue" key={`${issue.code}-${i}`}>
                  <small>
                    {readiness.errors.includes(issue) ? "Required" : "Note"}
                  </small>
                  <p>{issue.message}</p>
                  <button
                    className="text-link"
                    onClick={() => setTab(issue.section)}
                  >
                    Open {issue.section}
                  </button>
                </div>
              ))}
            </div>
          )}
        </aside>
      </div>
    </>
  );
}
