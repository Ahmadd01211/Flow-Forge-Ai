"use client";
import type { RecipeSample } from "@/features/templates/recipe-handoff";
import { useEffect, useLayoutEffect, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  Activity,
  ArrowLeft,
  BookOpen,
  Bot,
  Brain,
  Check,
  Cpu,
  FlaskConical,
  History,
  LoaderCircle,
  Rocket,
  Save,
  Send,
  Shapes,
  ShieldCheck,
  Sparkles,
  Wrench,
  X,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { ErrorNotice } from "@/components/shared/ui";
import { SaveTemplate } from "@/features/templates/save-template";
import {
  McpConnections,
  type McpListing,
} from "@/features/workspace/mcp-connections";
import { api } from "@/lib/api/client";
import { useUnsavedChanges } from "@/lib/use-unsaved-changes";
import type {
  Agent,
  AgentConfig,
  AgentVersion,
  Connection,
  VersionList,
} from "@/lib/api/types";
import type { ToolEntry } from "@/features/tools/tool-registry";
import type { HttpTool } from "@/features/tools/http-tool-registry";
import type { components } from "@/lib/api/generated";
import { VersionHistory } from "./version-history";
import { agentStarters } from "./agent-starters";
import type { McpServerOption } from "./model-tools";
import {
  Block,
  BrainBlock,
  GuardrailsBlock,
  IoBlock,
  MemoryBlock,
  PersonaBlock,
  ReadinessMeter,
  SkillsBlock,
} from "./builder-blocks";
import type { SkillItem } from "./skills-model";
import {
  IO_PRESETS,
  SECTION_BLOCK,
  blockReadiness,
  presetOf,
  toolCount,
  type BlockId,
} from "./builder-model";
import { ToolShelf } from "./tool-shelf";
import { TryPanel } from "./try-panel";
import { UsePanel } from "./use-panel";
import { LaunchChecklist } from "@/features/launch/launch-checklist";
import {
  deriveLaunchSteps,
  launchConfigKey,
  type LaunchFacts,
  type LaunchIssue,
  type SampleEvidence,
} from "@/features/launch/launch-model";
import { PerformanceBlock } from "./performance-block";

const defaultConfig: AgentConfig = {
  schema_version: 1,
  instructions: "",
  provider: "openai",
  model_id: "",
  tool_keys: [],
  mcp_tools: [],
  http_tools: [],
  memory: null,
  workflow_tools: [],
  skills: [],
  skill_loading: "on_demand",
  input_schema: IO_PRESETS[0].input as AgentConfig["input_schema"],
  output_schema: IO_PRESETS[0].output as AgentConfig["output_schema"],
  limits: {
    max_iterations: 8,
    timeout_seconds: 60,
    max_cost_usd: "0.10",
    max_tool_calls: 8,
    max_output_tokens: 4096,
  },
};

const PROVIDER_LABEL: Record<string, string> = {
  openai: "OpenAI",
  anthropic: "Claude",
  gemini: "Gemini",
  openrouter: "OpenRouter",
  deepseek: "DeepSeek",
};

function parseSchema(text: string): AgentConfig["input_schema"] | null {
  try {
    const value = JSON.parse(text);
    return value && typeof value === "object" && !Array.isArray(value)
      ? value
      : null;
  } catch {
    return null;
  }
}

export function AgentEditor({
  recipeSample,
  agent,
  workspaceId,
  versions,
  canEdit = true,
  canManage = false,
  connections = [],
  tools = [],
  mcpServers = [],
  mcpListing,
  httpTools = [],
  skills = [],
}: {
  recipeSample?: RecipeSample;
  agent?: Agent;
  workspaceId: string;
  versions?: VersionList;
  initialTab?: string;
  canEdit?: boolean;
  canManage?: boolean;
  connections?: Connection[];
  tools?: ToolEntry[];
  httpTools?: HttpTool[];
  mcpServers?: McpServerOption[];
  mcpListing?: McpListing;
  skills?: SkillItem[];
}) {
  const router = useRouter();
  const preferred = connections.find(
    (item) => item.state === "active" && item.default_model_id,
  );
  const initial =
    agent?.config ||
    (preferred
      ? {
          ...defaultConfig,
          provider: preferred.provider,
          model_id: preferred.default_model_id || "",
        }
      : defaultConfig);
  const [name, setName] = useState(agent?.name || ""),
    [description, setDescription] = useState(agent?.description || ""),
    [config, setConfig] = useState<AgentConfig>(initial),
    [input, setInput] = useState(JSON.stringify(initial.input_schema, null, 2)),
    [output, setOutput] = useState(
      JSON.stringify(initial.output_schema, null, 2),
    ),
    [revision, setRevision] = useState(agent?.revision || 1),
    [busy, setBusy] = useState(""),
    [error, setError] = useState(""),
    [summary, setSummary] = useState(""),
    [publishOpen, setPublishOpen] = useState(false),
    [drawer, setDrawer] = useState(false),
    [readiness, setReadiness] = useState<
      components["schemas"]["ReadinessRead"] | null
    >(null);
  const current = JSON.stringify({ name, description, config, input, output });
  const [baseline, setBaseline] = useState(current);
  const dirty = current !== baseline;
  useUnsavedChanges(dirty);

  const inputSchema = parseSchema(input),
    outputSchema = parseSchema(output);
  const schemasValid = !!inputSchema && !!outputSchema;
  const draft: AgentConfig = schemasValid
    ? { ...config, input_schema: inputSchema, output_schema: outputSchema }
    : config;
  const connection = connections.find(
    (item) => item.provider === config.provider,
  );
  const ready = blockReadiness(draft, connection, schemasValid);
  const published = versions?.items.find(
    (item) => item.purpose === "published",
  ) as AgentVersion | undefined;
  const status = !published
    ? { label: "Draft", tone: "draft" }
    : published.source_revision === revision && !dirty
      ? { label: `Published v${published.number}`, tone: "live" }
      : {
          label: `Unpublished changes · live v${published.number}`,
          tone: "changed",
        };

  const firstOpen =
    (Object.keys(ready) as BlockId[]).find((id) => !ready[id]) ??
    (agent ? null : "persona");
  const [open, setOpen] = useState<Set<string>>(
    () => new Set(firstOpen ? [firstOpen] : []),
  );
  function toggle(id: string) {
    setOpen((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }
  function reveal(id: string) {
    setOpen((current) => new Set(current).add(id));
    setTimeout(
      () =>
        document
          .getElementById(`block-${id}`)
          ?.scrollIntoView({
            behavior: window.matchMedia?.("(prefers-reduced-motion: reduce)")
              .matches
              ? "auto"
              : "smooth",
            block: "start",
          }),
      50,
    );
  }

  const configKey = launchConfigKey({ draft, input, output });
  const contextKey = launchConfigKey({ current, revision, id: agent?.id });
  const contextRef = useRef(contextKey);
  useLayoutEffect(() => {
    contextRef.current = contextKey;
  }, [contextKey]);
  const request = useRef(0);
  const pendingReadiness = useRef<{
    key: string;
    promise: Promise<void>;
  } | null>(null);
  const [checkState, setCheckState] =
    useState<LaunchFacts["check"]>("unchecked");
  const [sample, setSample] = useState<SampleEvidence | null>(null);
  const latestRequest = useRef<string | null>(null);
  const [evidenceKey, setEvidenceKey] = useState(configKey);
  if (evidenceKey !== configKey) {
    setEvidenceKey(configKey);
    setSample(null);
  }
  useLayoutEffect(() => {
    latestRequest.current = null;
  }, [configKey]);
  const serverDefinitionKey = launchConfigKey(
    agent && {
      name: agent.name,
      description: agent.description,
      config: agent.config,
    },
  );
  const serverContextKey = launchConfigKey({
    id: agent?.id,
    revision: agent?.revision,
    definition: serverDefinitionKey,
  });
  const receivedServerContext = useRef(serverContextKey);
  const savedDefinition = useRef(serverDefinitionKey);
  useLayoutEffect(() => {
    if (!agent || receivedServerContext.current === serverContextKey) return;
    receivedServerContext.current = serverContextKey;
    // The resource stays mounted across refreshes. Save acknowledgments preserve
    // the submitted sample and form; external definitions reconcile with edits.
    setRevision(agent.revision);
    if (savedDefinition.current === serverDefinitionKey) return;
    savedDefinition.current = serverDefinitionKey;
    const nextInput = JSON.stringify(agent.config.input_schema, null, 2);
    const nextOutput = JSON.stringify(agent.config.output_schema, null, 2);
    setBaseline(
      JSON.stringify({
        name: agent.name,
        description: agent.description,
        config: agent.config,
        input: nextInput,
        output: nextOutput,
      }),
    );
    if (dirty) {
      // Surface an external change while preserving the local draft.
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setError(
        "This agent changed on the server. Your unsaved edits are still here; review them before saving.",
      );
    } else {
      setName(agent.name);
      setDescription(agent.description);
      setConfig(agent.config);
      setInput(nextInput);
      setOutput(nextOutput);
    }
    request.current++;
    pendingReadiness.current = null;
    setCheckState("unchecked");
    setReadiness(null);
    latestRequest.current = null;
    setSample(null);
  }, [agent, dirty, serverContextKey, serverDefinitionKey]);
  function sampleEvent(evidence: SampleEvidence) {
    if (evidence.state === "running")
      latestRequest.current = evidence.requestId;
    if (latestRequest.current === evidence.requestId) setSample(evidence);
  }
  useEffect(() => {
    request.current++;
    pendingReadiness.current = null;
    // Invalidate the externally fetched readiness when its saved context changes.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setCheckState("unchecked");
    setReadiness(null);
  }, [contextKey]);
  useEffect(() => {
    let hidden = document.visibilityState === "hidden";
    const visibility = () => {
      if (document.visibilityState === "hidden") hidden = true;
      else if (hidden) {
        hidden = false;
        request.current++;
        pendingReadiness.current = null;
        setCheckState("unchecked");
        setReadiness(null);
        latestRequest.current = null;
        setSample(null);
      }
    };
    document.addEventListener("visibilitychange", visibility);
    return () => document.removeEventListener("visibilitychange", visibility);
  }, []);
  async function checkSetup() {
    if (!agent || dirty || !canEdit) return;
    if (pendingReadiness.current?.key === contextKey)
      return pendingReadiness.current.promise;
    const token = ++request.current,
      key = contextKey;
    setCheckState("checking");
    setReadiness(null);
    const promise = api<components["schemas"]["ReadinessRead"]>(
      `/workspaces/${workspaceId}/agents/${agent.id}/readiness`,
    )
      .then((result) => {
        if (request.current !== token || contextRef.current !== key) return;
        setReadiness(result);
        setCheckState(
          result.errors.length
            ? "blocked"
            : result.runnable
              ? "passed"
              : "setup_only",
        );
      })
      .catch((cause) => {
        if (request.current !== token || contextRef.current !== key) return;
        setCheckState("failed");
        setError(
          cause instanceof Error ? cause.message : "Could not check readiness.",
        );
      })
      .finally(() => {
        if (request.current === token) pendingReadiness.current = null;
      });
    pendingReadiness.current = { key, promise };
    return promise;
  }
  useEffect(() => {
    if (publishOpen) void checkSetup();
    // The same scoped request serves the checklist and publish dialog.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [publishOpen, contextKey]);
  function focusTarget(id: string) {
    setTimeout(() => {
      const element = document.getElementById(id);
      element?.scrollIntoView({
        behavior: window.matchMedia?.("(prefers-reduced-motion: reduce)")
          .matches
          ? "auto"
          : "smooth",
        block: "start",
      });
      const target =
        element?.querySelector<HTMLElement>(
          "button, input, textarea, select, a",
        ) ?? element;
      target?.focus();
    }, 50);
  }
  function reviewIssue(issue: LaunchIssue) {
    const block = issue.target && SECTION_BLOCK[issue.target];
    if (block) {
      reveal(block);
      focusTarget(`block-${block}`);
    } else {
      setPublishOpen(true);
      focusTarget("publish-diagnostics");
    }
  }
  const issues =
    readiness?.errors.map((issue) => ({
      code: issue.code,
      message: issue.message,
      target: issue.section,
    })) ?? [];
  const steps = deriveLaunchSteps({
    mode: "agent_test",
    saved: !!agent,
    dirty,
    canEdit,
    configKey,
    latestRequestId: sample?.requestId ?? null,
    check: checkState,
    issues,
    warnings: [],
    publishedCurrent: !!published && published.source_revision === revision,
    publishedVersionId: published?.id ?? null,
    sample,
  });

  function applyStarter(starter: (typeof agentStarters)[number]) {
    setName(starter.name);
    setDescription(starter.description);
    setConfig((previous) => ({
      ...previous,
      instructions: starter.instructions,
      ...(starter.memory ? { memory: starter.memory } : {}),
    }));
    setInput(JSON.stringify(starter.inputSchema, null, 2));
    setOutput(JSON.stringify(starter.outputSchema, null, 2));
  }

  async function save(): Promise<boolean> {
    if (!schemasValid) return false;
    setBusy("save");
    setError("");
    try {
      const result = await api<Agent>(
        `/workspaces/${workspaceId}/agents${agent ? `/${agent.id}` : ""}`,
        {
          method: agent ? "PATCH" : "POST",
          body: JSON.stringify({
            name,
            description,
            config: draft,
            ...(agent ? { expected_revision: revision } : {}),
          }),
        },
      );
      savedDefinition.current = launchConfigKey({
        name,
        description,
        config: result.config,
      });
      setConfig(result.config);
      setRevision(result.revision);
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
      return true;
    } catch (cause) {
      setError(
        cause instanceof Error ? cause.message : "Could not save this agent.",
      );
      return false;
    } finally {
      setBusy("");
    }
  }

  async function freeze(kind: "publish" | "snapshot") {
    if (!agent || dirty) return;
    setBusy(kind);
    setError("");
    try {
      await api<AgentVersion>(
        `/workspaces/${workspaceId}/agents/${agent.id}/${kind === "publish" ? "versions" : "test-snapshots"}`,
        {
          method: "POST",
          body: JSON.stringify({
            expected_revision: revision,
            change_summary: summary,
          }),
        },
      );
      setSummary("");
      setPublishOpen(false);
      reveal(kind === "publish" ? "use" : "history");
      router.refresh();
    } catch (cause) {
      setError(
        cause instanceof Error
          ? cause.message
          : kind === "publish"
            ? "Publication failed."
            : "Snapshot failed.",
      );
    } finally {
      setBusy("");
    }
  }

  const preset = IO_PRESETS.find((item) => item.id === presetOf(input, output));
  const firstLine = config.instructions.split("\n").find((line) => line.trim());
  return (
    <div className="agent-builder">
      <div className="builder-top">
        <Link
          href={`/w/${workspaceId}/agents`}
          className="icon-button"
          aria-label="Back to agents"
        >
          <ArrowLeft size={19} />
        </Link>
        <span className="builder-avatar" aria-hidden="true">
          <Bot size={22} />
        </span>
        <div className="builder-identity">
          <input
            className="builder-name"
            aria-label="Agent name"
            value={name}
            maxLength={100}
            placeholder="Name your agent"
            disabled={!canEdit}
            onChange={(event) => setName(event.target.value)}
          />
          <span className="row">
            <span className={`builder-status ${status.tone}`}>
              {status.label}
            </span>
            <small className="muted">
              {dirty
                ? "Unsaved changes"
                : agent
                  ? `Saved · revision ${revision}`
                  : "Not saved yet"}
            </small>
          </span>
        </div>
        <div className="row builder-actions">
          {agent && (
            <SaveTemplate
              workspaceId={workspaceId}
              sourceId={agent.id}
              kind="agent"
              revision={revision}
              name={name}
              description={description}
              disabled={!!busy || !canEdit || dirty}
            />
          )}
          <Button
            variant="outline"
            onClick={() => setPublishOpen(!publishOpen)}
            disabled={!agent || !canEdit}
            title={
              agent
                ? "Freeze these settings as a version"
                : "Save the agent first"
            }
          >
            <Rocket size={15} /> Publish
          </Button>
          <Button
            id="agent-save"
            onClick={save}
            disabled={
              !!busy ||
              !name.trim() ||
              !canEdit ||
              !schemasValid ||
              (!!agent && !dirty)
            }
          >
            {busy === "save" ? (
              <LoaderCircle size={15} className="spin" />
            ) : !dirty && agent ? (
              <Check size={15} />
            ) : (
              <Save size={15} />
            )}
            {!dirty && agent ? "Saved" : "Save"}
          </Button>
        </div>
      </div>
      {publishOpen && agent && (
        <section
          id="publish-diagnostics"
          tabIndex={-1}
          className="publish-bar"
          aria-label="Publish"
        >
          {dirty ? (
            <div className="row">
              <span>Save your changes first, then publish.</span>
              <Button
                size="sm"
                onClick={save}
                disabled={!!busy || !schemasValid}
              >
                <Save size={14} /> Save now
              </Button>
            </div>
          ) : (
            <>
              {readiness === null ? (
                <span className="muted">
                  <LoaderCircle size={13} className="spin" /> Checking provider,
                  tools and contracts…
                </span>
              ) : readiness.errors.length ? (
                <ul className="publish-issues">
                  {readiness.errors.map((issue) => (
                    <li key={issue.code + issue.message}>
                      <span>{issue.message}</span>
                      <button
                        type="button"
                        className="text-link"
                        onClick={() =>
                          reviewIssue({
                            code: issue.code,
                            message: issue.message,
                            target: issue.section,
                          })
                        }
                      >
                        Fix it
                      </button>
                    </li>
                  ))}
                </ul>
              ) : (
                <span className="publish-ok">
                  <ShieldCheck size={15} />{" "}
                  {readiness.runnable
                    ? "Everything checks out. Ready to publish."
                    : "Publishable, but this model is setup only and can't run yet."}
                </span>
              )}
              <div className="row">
                <input
                  aria-label="Version note"
                  placeholder="What changed? (optional)"
                  value={summary}
                  maxLength={1000}
                  onChange={(event) => setSummary(event.target.value)}
                />
                <Button
                  size="sm"
                  variant="outline"
                  disabled={!!busy || !config.instructions.trim()}
                  onClick={() => freeze("snapshot")}
                  title="Freeze without the provider check, for contract tests"
                >
                  {busy === "snapshot" ? (
                    <LoaderCircle size={14} className="spin" />
                  ) : (
                    <FlaskConical size={14} />
                  )}{" "}
                  Test snapshot
                </Button>
                <Button
                  size="sm"
                  disabled={!!busy || !readiness || readiness.errors.length > 0}
                  onClick={() => freeze("publish")}
                >
                  {busy === "publish" ? (
                    <LoaderCircle size={14} className="spin" />
                  ) : (
                    <Send size={14} />
                  )}{" "}
                  Publish version
                </Button>
              </div>
            </>
          )}
          <button
            type="button"
            className="icon-button publish-close"
            aria-label="Close"
            onClick={() => setPublishOpen(false)}
          >
            <X size={15} />
          </button>
        </section>
      )}
      {!agent && (
        <section className="builder-starters" aria-label="Agent quick starts">
          <strong>Start from a shape</strong>
          <div>
            {agentStarters.map((starter) => (
              <button
                key={starter.id}
                type="button"
                disabled={!canEdit}
                onClick={() => applyStarter(starter)}
              >
                <span aria-hidden="true">{starter.emoji}</span>
                <span>
                  <strong>{starter.name}</strong>
                  <small>{starter.description}</small>
                </span>
              </button>
            ))}
          </div>
        </section>
      )}
      {error && <ErrorNotice message={error} />}
      <LaunchChecklist
        steps={steps}
        issues={issues}
        warnings={
          readiness?.warnings.map((issue) => ({
            code: issue.code,
            message: issue.message,
            target: issue.section,
          })) ?? []
        }
        canEdit={canEdit}
        onIssue={reviewIssue}
        onAction={(action) => {
          if (action === "save") focusTarget("agent-save");
          else if (action === "check") {
            if (dirty || !agent) focusTarget("agent-save");
            else void checkSetup();
          } else if (action === "publish") setPublishOpen(true);
          else if (action === "sample" || action === "result")
            focusTarget("agent-sample");
          else reveal("brain");
        }}
      />
      <div className="builder-split">
        <div className="builder-blocks">
          <ReadinessMeter ready={ready} onOpen={reveal} />
          <Block
            id="persona"
            icon={<Sparkles size={16} />}
            title="Persona"
            summary={
              description || firstLine || "Give it a purpose and a voice"
            }
            done={ready.persona}
            open={open.has("persona")}
            onToggle={() => toggle("persona")}
          >
            <PersonaBlock
              config={config}
              setConfig={setConfig}
              description={description}
              setDescription={setDescription}
              canEdit={canEdit}
            />
          </Block>
          <Block
            id="brain"
            icon={<Cpu size={16} />}
            title="Brain"
            summary={
              config.model_id
                ? `${PROVIDER_LABEL[config.provider]} · ${config.model_id}`
                : "Choose a model"
            }
            done={ready.brain}
            open={open.has("brain")}
            onToggle={() => toggle("brain")}
          >
            <BrainBlock
              config={config}
              setConfig={setConfig}
              connections={connections}
              workspaceId={workspaceId}
              canEdit={canEdit}
            />
          </Block>
          <Block
            id="tools"
            icon={<Wrench size={16} />}
            title="Tools"
            summary={
              toolCount(config)
                ? `${toolCount(config)} tool${toolCount(config) === 1 ? "" : "s"} on`
                : "Optional · let it look things up and act"
            }
            done={ready.tools && toolCount(config) > 0}
            optional
            open={open.has("tools")}
            onToggle={() => toggle("tools")}
          >
            <ToolShelf
              grants={config}
              setGrants={(grants) => setConfig({ ...config, ...grants })}
              supported={
                !!connection?.model_capabilities[config.model_id]?.local_tools
              }
              unsupportedNote={
                config.model_id
                  ? `${config.model_id} can't call tools. Pick a model with the Tools badge in Brain.`
                  : "Choose a model first."
              }
              tools={tools}
              mcpServers={mcpServers}
              httpTools={httpTools}
              canEdit={canEdit}
              workspaceId={workspaceId}
              onConnect={
                mcpListing && canManage ? () => setDrawer(true) : undefined
              }
            />
          </Block>
          <Block
            id="skills"
            icon={<BookOpen size={16} />}
            title="Skills"
            summary={
              config.skills.length
                ? config.skills
                    .map((grant) => grant.name)
                    .filter(Boolean)
                    .join(", ")
                : "Optional · reusable know-how it loads when needed"
            }
            done={config.skills.length > 0}
            optional
            open={open.has("skills")}
            onToggle={() => toggle("skills")}
          >
            <SkillsBlock
              config={config}
              setConfig={setConfig}
              skills={skills}
              pinned={published?.config.skills}
              onDemand={
                connection?.model_capabilities[config.model_id]
                  ? !!connection.model_capabilities[config.model_id].local_tools
                  : null
              }
              workspaceId={workspaceId}
              canEdit={canEdit}
            />
          </Block>
          <Block
            id="memory"
            icon={<Brain size={16} />}
            title="Memory"
            summary={
              config.memory
                ? `Remembers ${config.memory.max_turns} exchanges by ${config.memory.key_pointer}`
                : "Optional · off"
            }
            done={!!config.memory && ready.memory}
            optional
            open={open.has("memory")}
            onToggle={() => toggle("memory")}
          >
            <MemoryBlock
              config={config}
              setConfig={setConfig}
              inputText={input}
              agentId={agent?.id}
              workspaceId={workspaceId}
              canEdit={canEdit}
              canManage={canManage}
            />
          </Block>
          <Block
            id="io"
            icon={<Shapes size={16} />}
            title="Input & output"
            summary={
              preset
                ? `${preset.emoji} ${preset.label}`
                : schemasValid
                  ? "🧩 Custom fields"
                  : "Fix the field definitions"
            }
            done={ready.io}
            open={open.has("io")}
            onToggle={() => toggle("io")}
          >
            <IoBlock
              input={input}
              output={output}
              setInput={setInput}
              setOutput={setOutput}
              strictOutput={
                config.provider === "openai" || config.provider === "openrouter"
              }
              canEdit={canEdit}
            />
          </Block>
          <Block
            id="guardrails"
            icon={<ShieldCheck size={16} />}
            title="Guardrails"
            summary={`$${Number(config.limits.max_cost_usd).toFixed(2)} per run · ${config.limits.max_tool_calls} tool calls · ${config.limits.timeout_seconds}s`}
            done={ready.guardrails}
            open={open.has("guardrails")}
            onToggle={() => toggle("guardrails")}
          >
            <GuardrailsBlock
              config={config}
              setConfig={setConfig}
              connection={connection}
              canEdit={canEdit}
            />
          </Block>
          {agent && (
            <Block
              id="performance"
              icon={<Activity size={16} />}
              title="Performance"
              summary="Runs, success, cost, tools and feedback"
              done={false}
              optional
              open={open.has("performance")}
              onToggle={() => toggle("performance")}
            >
              <PerformanceBlock workspaceId={workspaceId} agentId={agent.id} />
            </Block>
          )}
          {agent && versions && (
            <Block
              id="history"
              icon={<History size={16} />}
              title="History"
              summary={`${versions.items.length} version${versions.items.length === 1 ? "" : "s"}`}
              done={false}
              optional
              open={open.has("history")}
              onToggle={() => toggle("history")}
            >
              <VersionHistory
                key={`${agent.id}-${versions.items[0]?.id || "empty"}`}
                agent={{ ...agent, revision }}
                initial={versions}
                dirty={dirty}
                canEdit={canEdit}
                connections={connections}
              />
            </Block>
          )}
          {agent && (
            <Block
              id="use"
              icon={<Rocket size={16} />}
              title="Use it"
              summary={
                published
                  ? "Chat, call from your app, or add to a workflow"
                  : "Publish to use it"
              }
              done={!!published}
              optional
              open={open.has("use")}
              onToggle={() => toggle("use")}
            >
              <UsePanel
                workspaceId={workspaceId}
                agentId={agent.id}
                published={published}
              />
            </Block>
          )}
        </div>
        <aside id="agent-sample" tabIndex={-1} className="builder-try">
          <TryPanel
            recipeSample={recipeSample}
            configKey={configKey}
            onSampleEvent={sampleEvent}
            workspaceId={workspaceId}
            agentId={agent?.id}
            config={draft}
            schemasValid={schemasValid}
            canEdit={canEdit}
          />
        </aside>
      </div>
      {drawer && mcpListing && (
        <div
          className="builder-drawer"
          role="dialog"
          aria-label="Connect an MCP server"
        >
          <div className="builder-drawer-panel">
            <header>
              <strong>Connect a server</strong>
              <button
                type="button"
                className="icon-button"
                aria-label="Close"
                onClick={() => {
                  setDrawer(false);
                  router.refresh();
                }}
              >
                <X size={16} />
              </button>
            </header>
            <McpConnections
              workspaceId={workspaceId}
              initial={mcpListing}
              canManage={canManage}
              canTest={canEdit}
            />
          </div>
        </div>
      )}
    </div>
  );
}
