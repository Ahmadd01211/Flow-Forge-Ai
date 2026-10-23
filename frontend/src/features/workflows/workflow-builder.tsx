"use client";
import { memo, useCallback, useState } from "react";
import Link from "next/link";
import {
  addEdge,
  Background,
  BackgroundVariant,
  Controls,
  Handle,
  MiniMap,
  Position,
  ReactFlow,
  useEdgesState,
  useNodesState,
  type Connection,
  type Edge,
  type Node,
  type NodeProps,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import {
  AlertCircle,
  ArrowLeft,
  ArrowRight,
  Bot,
  Braces,
  Check,
  ChevronDown,
  ChevronRight,
  CircleDot,
  Code2,
  GitBranch,
  FileJson,
  FileText,
  ListFilter,
  List,
  LoaderCircle,
  LockKeyhole,
  MoreHorizontal,
  Play,
  PlugZap,
  Plus,
  RotateCcw,
  Save,
  Search,
  Settings2,
  ShieldCheck,
  Trash2,
  Workflow as WorkflowIcon,
  X,
  Zap,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge, ErrorNotice } from "@/components/shared/ui";
import { api } from "@/lib/api/client";
import { useUnsavedChanges } from "@/lib/use-unsaved-changes";
import { connectInsertedNode } from "./graph-edit";
import type {
  Graph,
  GraphNode,
  NodeKind,
  Validation,
  Workflow,
} from "@/lib/api/types";

type CanvasNode = Node<{ definition: GraphNode }, "flowforge">;
const kinds: {
  type: NodeKind;
  name: string;
  description: string;
  icon: typeof Bot;
  tone: string;
  group: string;
  enabled: boolean;
}[] = [
  {
    type: "manual_input",
    name: "Manual input",
    description: "Start with structured data",
    icon: Zap,
    tone: "teal",
    group: "TRIGGERS",
    enabled: true,
  },
  {
    type: "webhook_trigger",
    name: "Webhook trigger",
    description: "Start when your app sends an HTTP event",
    icon: PlugZap,
    tone: "teal",
    group: "TRIGGERS",
    enabled: true,
  },
  {
    type: "schedule_trigger",
    name: "Schedule trigger",
    description: "Start on a recurring schedule",
    icon: CircleDot,
    tone: "teal",
    group: "TRIGGERS",
    enabled: true,
  },
  {
    type: "agent",
    name: "AI agent",
    description: "Run a published agent with approved tools",
    icon: Bot,
    tone: "purple",
    group: "INTELLIGENCE",
    enabled: true,
  },
  {
    type: "condition",
    name: "Condition",
    description: "Route true and false paths",
    icon: GitBranch,
    tone: "amber",
    group: "LOGIC",
    enabled: true,
  },
  {
    type: "transform",
    name: "Transform",
    description: "Build an object from literals and input fields",
    icon: Braces,
    tone: "blue",
    group: "LOGIC",
    enabled: true,
  },
  {
    type: "text_template",
    name: "Text template",
    description: "Compose messages from workflow data",
    icon: FileText,
    tone: "blue",
    group: "DATA",
    enabled: true,
  },
  {
    type: "list_filter",
    name: "List filter",
    description: "Keep matching items in an array",
    icon: ListFilter,
    tone: "amber",
    group: "DATA",
    enabled: true,
  },
  {
    type: "json_parse",
    name: "Parse JSON",
    description: "Turn JSON text into structured data",
    icon: FileJson,
    tone: "blue",
    group: "DATA",
    enabled: true,
  },
  {
    type: "tool",
    name: "Approved tool",
    description: "Runs when approved in Tool Registry",
    icon: Code2,
    tone: "blue",
    group: "TOOLS",
    enabled: true,
  },
  {
    type: "mcp_tool",
    name: "MCP tool",
    description: "Call an approved read-only service tool",
    icon: PlugZap,
    tone: "purple",
    group: "TOOLS",
    enabled: true,
  },
  {
    type: "result",
    name: "Return result",
    description: "A structured final output",
    icon: ArrowRight,
    tone: "slate",
    group: "OUTPUT",
    enabled: true,
  },
];
const FlowNode = memo(function FlowNode({
  data,
  selected,
}: NodeProps<CanvasNode>) {
  const d = data.definition,
    kind = kinds.find((k) => k.type === d.type)!;
  const Icon = kind.icon;
  return (
    <div className={`flowforge-node ${selected ? "selected" : ""}`}>
      <div className="flow-node-top">
        <span className={`node-icon ${kind.tone}`}>
          <Icon size={19} />
        </span>
        <span className="flow-node-category">{kind.name.toUpperCase()}</span>
        <MoreHorizontal size={15} />
      </div>
      <strong>{d.label}</strong>
      <p>
        {d.type === "agent"
          ? "Select a published agent version"
          : d.type === "condition"
            ? "Compare values and select a path"
            : d.type === "transform"
              ? "Structured field mapping"
              : d.type === "text_template"
                ? "Compose text from input fields"
                : d.type === "list_filter"
                  ? "Select matching list items"
                  : d.type === "json_parse"
                    ? "Parse a JSON string"
                : d.type === "mcp_tool"
                  ? "Call a reviewed remote tool"
                : d.type === "result"
                ? "Return workflow output"
                  : d.type === "webhook_trigger"
                    ? "Receive an HTTP event"
                    : d.type === "schedule_trigger"
                      ? "Run on a schedule"
                : "Provide workflow input"}
      </p>
      <div className="flow-node-footer">
        <span className="node-state-dot" />
        Draft configuration{d.type === "agent" && <LockKeyhole size={11} />}
      </div>
      {d.type !== "manual_input" && d.type !== "webhook_trigger" && d.type !== "schedule_trigger" && (
        <Handle type="target" position={Position.Left} id="in" />
      )}
      {d.type !== "result" &&
        (d.type === "condition" ? (
          <>
            <Handle
              type="source"
              position={Position.Right}
              id="true"
              style={{ top: "37%" }}
            />
            <span className="port-label true">true</span>
            <Handle
              type="source"
              position={Position.Right}
              id="false"
              style={{ top: "75%" }}
            />
            <span className="port-label false">false</span>
          </>
        ) : (
          <Handle type="source" position={Position.Right} id="out" />
        ))}
    </div>
  );
});
const nodeTypes = { flowforge: FlowNode };
function canvasNodes(graph: Graph): CanvasNode[] {
  return graph.nodes.map((n) => ({
    id: n.id,
    type: "flowforge",
    position: n.position,
    data: { definition: n },
  }));
}
function canvasEdges(graph: Graph): Edge[] {
  return graph.edges.map((e) => ({
    id: e.id,
    source: e.source,
    target: e.target,
    sourceHandle: e.source_port,
    targetHandle: e.target_port,
    data: { mappings: e.mappings },
    type: "smoothstep",
  }));
}

export function WorkflowBuilder({ workflow, agentOptions, mcpOptions, initialPublishedVersion }: { workflow: Workflow; agentOptions: { id: string; name: string; number: number; provider: string; model_id: string; tool_keys: string[] }[]; mcpOptions: { id: string; name: string; runnable_tools: string[]; runnable_schemas: Record<string, unknown> }[]; initialPublishedVersion: string | null }) {
  const [nodes, setNodes, onNodesChange] = useNodesState<CanvasNode>(
      canvasNodes(workflow.graph),
    ),
    [edges, setEdges, onEdgesChange] = useEdgesState(
      canvasEdges(workflow.graph),
    );
  const [name, setName] = useState(workflow.name),
    [revision, setRevision] = useState(workflow.revision),
    [selected, setSelected] = useState<string | null>(workflow.graph.nodes.find((node) => ["manual_input", "webhook_trigger", "schedule_trigger"].includes(node.type))?.id || null),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [validation, setValidation] = useState<Validation | null>(null),
    [panel, setPanel] = useState(true),
    [query, setQuery] = useState(""),
    [inspectorTab, setInspectorTab] = useState("configuration"),
    [configText, setConfigText] = useState(JSON.stringify(workflow.graph.nodes.find((node) => ["manual_input", "webhook_trigger", "schedule_trigger"].includes(node.type))?.config || {}, null, 2)),
    [listView, setListView] = useState(false),
    [target, setTarget] = useState(""),
    [port, setPort] = useState("out"),
    [history, setHistory] = useState<Graph[]>([]),
    [paletteOpen, setPaletteOpen] = useState(false);
  const [previewInput, setPreviewInput] = useState(
    '{"text":"Hello world","find":"world","replacement":"FlowForge"}',
  );
  const [previewResult, setPreviewResult] = useState<{
    output: unknown;
    steps: { node_id: string; type: string; status: string; output: unknown }[];
  } | null>(null);
  const [publishedVersion, setPublishedVersion] = useState<string | null>(initialPublishedVersion);
  const [durableRun, setDurableRun] = useState<{
    id: string;
    state: string;
    output: unknown;
    steps: { node_id: string; status: string }[] | null;
    error_code: string | null;
    cost_usd: string | null;
    uncertain_cost_usd: string | null;
    input_tokens: number | null;
    output_tokens: number | null;
  } | null>(null);
  const graph: Graph = {
    ...workflow.graph,
    nodes: nodes.map((n) => ({ ...n.data.definition, position: n.position })),
    edges: edges.map((e) => ({
      id: e.id,
      source: e.source,
      source_port: (e.sourceHandle || "out") as "out" | "true" | "false",
      target: e.target,
      target_port: "in",
      mappings: (e.data?.mappings || []) as { from: string; to: string }[],
    })),
  };
  const snapshot = JSON.stringify({ name, graph }),
    [baseline, setBaseline] = useState(snapshot),
    dirty = snapshot !== baseline;
  useUnsavedChanges(dirty);
  const active = nodes.find((n) => n.id === selected),
    activeKind = kinds.find((k) => k.type === active?.data.definition.type);
  function remember() {
    setHistory((h) => [...h.slice(-29), structuredClone(graph)]);
    setValidation(null);
  }
  function selectNode(id: string) {
    setSelected(id);
    setConfigText(
      JSON.stringify(
        nodes.find((n) => n.id === id)?.data.definition.config || {},
        null,
        2,
      ),
    );
    setInspectorTab("configuration");
  }
  function addNode(type: NodeKind) {
    if (type === "result" && nodes.some((n) => n.data.definition.type === type)) return;
    if (["manual_input", "webhook_trigger", "schedule_trigger"].includes(type) && nodes.some((n) => ["manual_input", "webhook_trigger", "schedule_trigger"].includes(n.data.definition.type))) {
      setError("A workflow can have one trigger. Remove the existing trigger first.");
      return;
    }
    if (type === "condition" && nodes.some((n) => n.data.definition.type === "condition")) {
      setError("Published workflows currently support one condition node.");
      return;
    }
    remember();
    const kind = kinds.find((k) => k.type === type)!;
    const id = `${type}-${crypto.randomUUID().slice(0, 8)}`;
    const selectedNode = nodes.find((n) => n.id === selected);
    const source = selectedNode?.data.definition.type === "result"
      ? nodes.find((n) => n.id === edges.find((edge) => edge.target === selectedNode.id)?.source)
      : selectedNode;
    const branchPort = port === "false" ? "false" : "true";
    const outgoing = source
      ? edges.filter((edge) => edge.source === source.id && (source.data.definition.type !== "condition" || edge.sourceHandle === branchPort))
      : [];
    const next = outgoing.length === 1 ? nodes.find((n) => n.id === outgoing[0].target) : undefined;
    const config: Record<string, unknown> =
      type === "condition"
        ? {
            operator: "eq",
            left: { kind: "literal", value: true },
            right: { kind: "literal", value: true },
          }
        : type === "agent"
          ? { version_id: "" }
        : type === "transform"
          ? {
              fields: { message: { kind: "literal", value: "" } },
              output_schema: {
                type: "object",
                properties: { message: { type: "string" } },
              },
            }
          : type === "text_template"
            ? { template: "Ticket {{/ticket/id}} is ready." }
          : type === "list_filter"
            ? { source: "/items", item_pointer: "/status", operator: "eq", value: "open" }
          : type === "json_parse"
            ? { source: "/text" }
          : type === "tool"
            ? { tool_key: "text.replace" }
            : type === "mcp_tool"
              ? { server_id: mcpOptions.find((option) => option.runnable_tools.length)?.id || "", tool_name: mcpOptions.find((option) => option.runnable_tools.length)?.runnable_tools[0] || "" }
            : type === "result"
              ? { value: { kind: "output", node_id: "input", pointer: "" } }
              : {};
    const definition: GraphNode = {
      id,
      type,
      label: kind.name,
      config,
      position: {
        x: source ? next ? (source.position.x + next.position.x) / 2 : source.position.x + 280 : 240 + (nodes.length % 3) * 100,
        y: source ? next ? (source.position.y + next.position.y) / 2 + 80 : source.position.y + 120 : 100 + nodes.length * 60,
      },
      join: "all",
      policy: { timeout_seconds: 60, max_attempts: 1 },
    };
    setNodes((n) => [
      ...n.map((existing) => next?.id === existing.id && existing.data.definition.type === "result"
        ? { ...existing, data: { definition: { ...existing.data.definition, config: type === "condition" || edges.filter((edge) => edge.target === next?.id).length > 1 ? {} : { value: { kind: "output", node_id: id, pointer: "" } } } } }
        : existing),
      {
        id,
        type: "flowforge",
        position: definition.position,
        data: { definition },
      },
    ]);
    if (source && source.data.definition.type !== "result") {
      if (outgoing.length === 1 && next) {
        if (type === "condition") {
          setEdges((current) => [
            ...current.map((edge) => edge.id === outgoing[0].id ? { ...edge, target: id } : edge),
            ...(["true", "false"] as const).map((branch) => ({
              id: `edge-${crypto.randomUUID()}`, source: id, target: next.id,
              sourceHandle: branch, targetHandle: "in", type: "smoothstep" as const,
              data: { mappings: [] },
            })),
          ]);
        } else {
          setEdges((current) => connectInsertedNode(current, source.id, id, outgoing[0], `edge-${crypto.randomUUID()}`));
        }
      } else if (outgoing.length === 0) {
        setEdges((current) => [...current, {
          id: `edge-${crypto.randomUUID()}`, source: source.id, target: id,
          sourceHandle: source.data.definition.type === "condition" ? branchPort : "out",
          targetHandle: "in", type: "smoothstep", data: { mappings: [] },
        }]);
      }
    }
    setSelected(id);
    setConfigText(JSON.stringify(config, null, 2));
    setPaletteOpen(false);
  }
  const connect = useCallback(
    (connection: Connection) => {
      setEdges((es) =>
        addEdge(
          {
            ...connection,
            id: `edge-${crypto.randomUUID()}`,
            type: "smoothstep",
            data: { mappings: [] },
          },
          es,
        ),
      );
      setValidation(null);
    },
    [setEdges],
  );
  function updateNode(update: Partial<GraphNode>) {
    setNodes((ns) =>
      ns.map((n) =>
        n.id === selected
          ? { ...n, data: { definition: { ...n.data.definition, ...update } } }
          : n,
      ),
    );
    setValidation(null);
  }
  function removeNode() {
    if (!selected) return;
    remember();
    setNodes((ns) => ns.filter((n) => n.id !== selected));
    setEdges((es) =>
      es.filter((e) => e.source !== selected && e.target !== selected),
    );
    setSelected(null);
  }
  function undo() {
    const previous = history.at(-1);
    if (!previous) return;
    setNodes(canvasNodes(previous));
    setEdges(canvasEdges(previous));
    setHistory((h) => h.slice(0, -1));
    setSelected(null);
    setValidation(null);
  }
  async function save(): Promise<Workflow | null> {
    setBusy(true);
    setError("");
    try {
      const result = await api<Workflow>(
        `/workspaces/${workflow.workspace_id}/workflows/${workflow.id}`,
        {
          method: "PATCH",
          body: JSON.stringify({
            name,
            description: workflow.description,
            expected_revision: revision,
            graph,
          }),
        },
      );
      setRevision(result.revision);
      setPublishedVersion(null);
      setDurableRun(null);
      setBaseline(JSON.stringify({ name: result.name, graph: result.graph }));
      return result;
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not save workflow.");
      return null;
    } finally {
      setBusy(false);
    }
  }
  async function validate() {
    setPanel(true);
    let currentRevision = revision;
    if (dirty) {
      const saved = await save();
      if (!saved) return;
      currentRevision = saved.revision;
    }
    setBusy(true);
    setError("");
    try {
      const result = await api<Validation>(
        `/workspaces/${workflow.workspace_id}/workflows/${workflow.id}/validate`,
        {
          method: "POST",
          body: JSON.stringify({ expected_revision: currentRevision }),
        },
      );
      setValidation(result);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Validation unavailable.");
    } finally {
      setBusy(false);
    }
  }
  async function preview() {
    setPanel(true);
    setPreviewResult(null);
    let parsed: unknown;
    try {
      parsed = JSON.parse(previewInput);
      if (!parsed || typeof parsed !== "object" || Array.isArray(parsed))
        throw new Error("Preview input must be a JSON object.");
    } catch (cause) {
      setError(
        cause instanceof Error ? cause.message : "Enter valid JSON input.",
      );
      return;
    }
    let currentRevision = revision;
    if (dirty) {
      const saved = await save();
      if (!saved) return;
      currentRevision = saved.revision;
    }
    setBusy(true);
    setError("");
    try {
      const result = await api<{
        output: unknown;
        steps: {
          node_id: string;
          type: string;
          status: string;
          output: unknown;
        }[];
      }>(
        `/workspaces/${workflow.workspace_id}/workflows/${workflow.id}/preview`,
        {
          method: "POST",
          body: JSON.stringify({
            expected_revision: currentRevision,
            input: parsed,
          }),
        },
      );
      setPreviewResult(result);
    } catch (cause) {
      setError(
        cause instanceof Error ? cause.message : "Preview could not run.",
      );
    } finally {
      setBusy(false);
    }
  }
  async function publish() {
    let currentRevision = revision;
    if (dirty) {
      const saved = await save();
      if (!saved) return;
      currentRevision = saved.revision;
    }
    setBusy(true);
    setError("");
    try {
      const version = await api<{ id: string; number: number }>(
        `/workspaces/${workflow.workspace_id}/workflows/${workflow.id}/versions`,
        {
          method: "POST",
          body: JSON.stringify({ expected_revision: currentRevision }),
        },
      );
      setPublishedVersion(version.id);
      setDurableRun(null);
    } catch (cause) {
      setError(
        cause instanceof Error ? cause.message : "Could not publish workflow.",
      );
    } finally {
      setBusy(false);
    }
  }
  async function runPublished() {
    if (!publishedVersion) return;
    let parsed: unknown;
    try {
      parsed = JSON.parse(previewInput);
      if (!parsed || typeof parsed !== "object" || Array.isArray(parsed))
        throw new Error("Run input must be a JSON object.");
    } catch (cause) {
      setError(
        cause instanceof Error ? cause.message : "Enter valid JSON input.",
      );
      return;
    }
    setBusy(true);
    setError("");
    setPanel(true);
    try {
      const path = `/workspaces/${workflow.workspace_id}/workflow-runs`;
      let run = await api<{
        id: string;
        state: string;
        output: unknown;
        steps: { node_id: string; status: string }[] | null;
        error_code: string | null;
        cost_usd: string | null;
        uncertain_cost_usd: string | null;
        input_tokens: number | null;
        output_tokens: number | null;
      }>(path, {
        method: "POST",
        headers: { "Idempotency-Key": crypto.randomUUID() },
        body: JSON.stringify({ version_id: publishedVersion, input: parsed }),
      });
      setDurableRun(run);
      for (
        let i = 0;
        i < 35 && (run.state === "queued" || run.state === "running");
        i++
      ) {
        await new Promise((resolve) => setTimeout(resolve, 1000));
        run = await api<typeof run>(`${path}/${run.id}`);
        setDurableRun(run);
      }
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Workflow run failed.");
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="workflow-editor">
      <div className="builder-toolbar">
        <div className="builder-title">
          <Link
            href={`/w/${workflow.workspace_id}/workflows`}
            className="icon-button"
            aria-label="Back to workflows"
          >
            <ArrowLeft size={18} />
          </Link>
          <div>
            <div className="row">
              <span className="muted">Workflows</span>
              <ChevronRight size={12} />
              <span>{workflow.name}</span>
            </div>
            <div className="row">
              <strong>{name}</strong>
              <Badge>Draft</Badge>
              <span className="save-state">
                {dirty ? "Unsaved changes" : `Saved · revision ${revision}`}
              </span>
            </div>
          </div>
        </div>
        <div className="builder-actions">
          <Button
            variant="ghost"
            size="sm"
            onClick={undo}
            disabled={!history.length}
            title="Undo last graph edit"
          >
            <RotateCcw size={16} />
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={save}
            disabled={busy || !dirty}
          >
            {busy ? (
              <LoaderCircle size={15} className="spin" />
            ) : (
              <Save size={15} />
            )}
            Save
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={validate}
            disabled={busy}
          >
            <ShieldCheck size={15} />
            {dirty ? "Save & validate" : "Validate"}
          </Button>
          <Button variant="outline" size="sm" onClick={preview} disabled={busy || nodes.some((node) => node.data.definition.type === "agent")} title={nodes.some((node) => node.data.definition.type === "agent") ? "Agent steps require a published workflow run. Publish and use Run." : "Preview local steps without creating a run."}>
            <Play size={14} />
            Preview
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={publish}
            disabled={busy}
            title="Publish a validated linear workflow with approved local tools and up to one agent."
          >
            <LockKeyhole size={13} />
            Publish
          </Button>
          <Button
            size="sm"
            onClick={runPublished}
            disabled={busy || !publishedVersion || dirty}
            title="Run the last version published in this editor."
          >
            <Play size={14} />
            Run
          </Button>
        </div>
      </div>
      {error && (
        <div className="builder-error">
          <ErrorNotice message={error} />
        </div>
      )}
      <div className="builder-workspace">
        <aside className={`node-palette ${paletteOpen ? "mobile-open" : ""}`}>
          <div className="palette-heading">
            <h2>Node library</h2>
            <button
              className="icon-button palette-close"
              onClick={() => setPaletteOpen(false)}
              aria-label="Close node library"
            >
              <X size={17} />
            </button>
          </div>
          <p className="muted">The building blocks of your flow.</p>
          <p className="palette-guidance">Select a step, then add a node to insert it into the path. Save, validate and preview when ready.</p>
          <div className="search-input">
            <Search size={15} />
            <input
              aria-label="Search nodes"
              placeholder="Find a node…"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
          </div>
          {[...new Set(kinds.map((k) => k.group))].map((group) => (
            <div className="palette-group" key={group}>
              <h3>{group}</h3>
              {kinds
                .filter(
                  (k) =>
                    k.group === group &&
                    `${k.name} ${k.description}`
                      .toLowerCase()
                      .includes(query.toLowerCase()),
                )
                .map((k) => (
                  <button
                    key={k.type}
                    className="palette-node"
                    disabled={!k.enabled || ((k.type === "manual_input" || k.type === "result") && nodes.some((n) => n.data.definition.type === k.type))}
                    onClick={() => addNode(k.type)}
                    title={k.enabled ? `Add ${k.name}${selected ? " after the selected step" : ""}` : k.description}
                  >
                    <span className={`node-icon ${k.tone}`}>
                      <k.icon size={18} />
                    </span>
                    <span>
                      <strong>{k.name}</strong>
                      <small>{k.description}</small>
                    </span>
                    {k.enabled ? <Plus size={13} /> : <LockKeyhole size={12} />}
                  </button>
                ))}
            </div>
          ))}
          <div className="palette-tip">
            <CircleDot size={17} />
            <p>
              Select a step, then click to insert a node.
              <br />
              Drag its handles to connect.
            </p>
          </div>
        </aside>
        <section className="canvas-area" aria-label="Workflow graph editor">
          <div className="canvas-top">
            <div className="canvas-view-switch">
              <button
                className={!listView ? "active" : ""}
                onClick={() => setListView(false)}
              >
                <WorkflowIcon size={14} />
                Canvas
              </button>
              <button
                className={listView ? "active" : ""}
                onClick={() => setListView(true)}
              >
                <List size={14} />
                Steps
              </button>
            </div>
            <button
              className="mobile-palette-toggle button button-outline button-sm"
              onClick={() => setPaletteOpen(true)}
            >
              <Plus size={14} />
              Add node
            </button>
            <span className="canvas-summary">
              {nodes.length} nodes <span>·</span> {edges.length} connections
            </span>
          </div>
          <div className="canvas-body">
            {listView ? (
              <div className="accessible-node-list">
                <h2>Workflow steps</h2>
                <p>
                  Select a step to configure it or create a connection in the
                  inspector.
                </p>
                {nodes.map((n) => (
                  <button
                    className={selected === n.id ? "selected" : ""}
                    onClick={() => selectNode(n.id)}
                    key={n.id}
                  >
                    <span
                      className={`node-icon ${kinds.find((k) => k.type === n.data.definition.type)?.tone}`}
                    >
                      <Settings2 size={17} />
                    </span>
                    <div>
                      <strong>{n.data.definition.label}</strong>
                      <span>
                        {n.data.definition.type} ·{" "}
                        {edges.filter((e) => e.source === n.id).length} outgoing
                        connections
                      </span>
                    </div>
                    <ChevronRight size={16} />
                  </button>
                ))}
              </div>
            ) : (
              <ReactFlow
                nodes={nodes}
                edges={edges}
                nodeTypes={nodeTypes}
                onNodesChange={(changes) => {
                  if (changes.some((c) => c.type === "remove")) remember();
                  onNodesChange(changes);
                }}
                onEdgesChange={(changes) => {
                  if (changes.some((c) => c.type === "remove")) remember();
                  onEdgesChange(changes);
                }}
                onNodeDragStart={remember}
                onConnect={(connection) => {
                  remember();
                  connect(connection);
                }}
                onNodeClick={(_, node) => selectNode(node.id)}
                onPaneClick={() => setSelected(null)}
                onSelectionChange={({ nodes: selection }) => {
                  if (selection.length === 1 && selection[0].id !== selected)
                    selectNode(selection[0].id);
                }}
                fitView
                fitViewOptions={{ padding: 0.35, maxZoom: 1 }}
                minZoom={0.25}
                maxZoom={1.75}
                defaultEdgeOptions={{
                  style: { stroke: "#a3aec2", strokeWidth: 1.7 },
                }}
                deleteKeyCode={["Backspace", "Delete"]}
                aria-label="Editable workflow canvas"
              >
                <Background
                  variant={BackgroundVariant.Dots}
                  gap={20}
                  size={1.2}
                  color="#d4dbe8"
                />
                <Controls showInteractive={false} />
                <MiniMap
                  nodeColor="#d9d4ff"
                  maskColor="rgba(246,248,252,0.7)"
                  pannable
                  zoomable
                />
              </ReactFlow>
            )}
          </div>
          <div className="canvas-bottom">
            <span>
              <ShieldCheck size={13} /> Draft editor · no actions are executed
            </span>
            <button onClick={() => setPanel(!panel)}>
              Validation <ChevronDown size={13} />
            </button>
          </div>
        </section>
        <aside className="node-inspector">
          <div className="inspector-heading">
            <h2>{active ? "Node configuration" : "Workflow configuration"}</h2>
            {active && (
              <button
                className="icon-button"
                onClick={() => setSelected(null)}
                aria-label="Close node configuration"
              >
                <X size={16} />
              </button>
            )}
          </div>
          {active && activeKind ? (
            <>
              <div className="inspector-node-title">
                <span className={`node-icon ${activeKind.tone}`}>
                  <activeKind.icon size={22} />
                </span>
                <div>
                  <strong>{active.data.definition.label}</strong>
                  <span>{activeKind.name}</span>
                </div>
              </div>
              <div className="inspector-tabs">
                <button
                  className={inspectorTab === "configuration" ? "active" : ""}
                  onClick={() => setInspectorTab("configuration")}
                >
                  Configuration
                </button>
                <button
                  className={inspectorTab === "policy" ? "active" : ""}
                  onClick={() => setInspectorTab("policy")}
                >
                  Policies
                </button>
              </div>
              <div className="inspector-content">
                {inspectorTab === "configuration" ? (
                  <>
                    <label>
                      Node name
                      <input
                        value={active.data.definition.label}
                        maxLength={100}
                        onFocus={remember}
                        onChange={(e) => updateNode({ label: e.target.value })}
                      />
                    </label>
                    <label>
                      Join behavior
                      <select
                        value={active.data.definition.join}
                        onChange={(e) => {
                          remember();
                          updateNode({
                            join: e.target.value as "all" | "active",
                          });
                        }}
                      >
                        <option value="all">All paths must be active</option>
                        <option value="active">Merge active paths</option>
                      </select>
                    </label>
                    {active.data.definition.type === "agent" && (
                      <div className="agent-node-picker">
                        <label>
                          Published agent version
                          <select
                            value={String(active.data.definition.config.version_id || "")}
                            onChange={(event) => {
                              remember();
                              const config = { ...active.data.definition.config, version_id: event.target.value };
                              updateNode({ config });
                              setConfigText(JSON.stringify(config, null, 2));
                            }}
                          >
                            <option value="">Choose an agent version</option>
                            {agentOptions.map((option) => (
                              <option key={option.id} value={option.id}>{option.name} · v{option.number} · {option.provider}/{option.model_id}{option.tool_keys.length ? ` · ${option.tool_keys.length} tools` : ""}</option>
                            ))}
                          </select>
                        </label>
                        <p>Select an immutable published agent. Its provider key, input schema, tool approvals and budget are checked again at run time. Tool calls currently work with OpenAI GPT-5 Mini.</p>
                        <Link href={`/w/${workflow.workspace_id}/agents/new`} className="text-link">{agentOptions.length ? "Create another agent" : "Create and publish an agent first"}</Link>
                      </div>
                    )}
                    {active.data.definition.type === "mcp_tool" && (
                      <div className="agent-node-picker">
                        <label>
                          Approved MCP tool
                          <select
                            value={`${String(active.data.definition.config.server_id || "")}:${String(active.data.definition.config.tool_name || "")}`}
                            onChange={(event) => {
                              const [server_id, tool_name] = event.target.value.split(":", 2);
                              remember();
                              const config = { server_id, tool_name };
                              updateNode({ config });
                              setConfigText(JSON.stringify(config, null, 2));
                            }}
                          >
                            <option value=":">Choose a connected read-only tool</option>
                            {mcpOptions.flatMap((server) => server.runnable_tools.map((tool) => (
                              <option key={`${server.id}:${tool}`} value={`${server.id}:${tool}`}>{server.name} · {tool}</option>
                            )))}
                          </select>
                        </label>
                        <p>The workflow pins this connection generation and tool schema when published. Changes require a new workflow version.</p>
                        {mcpOptions.find((server) => server.id === active.data.definition.config.server_id)?.runnable_schemas[String(active.data.definition.config.tool_name || "")] !== undefined && (
                          <pre className="tool-output">{JSON.stringify(mcpOptions.find((server) => server.id === active.data.definition.config.server_id)?.runnable_schemas[String(active.data.definition.config.tool_name || "")], null, 2)}</pre>
                        )}
                        {!mcpOptions.some((server) => server.runnable_tools.length) && <Link href={`/w/${workflow.workspace_id}/integrations`} className="text-link">Connect an approved MCP service</Link>}
                      </div>
                    )}
                    <label>
                      Configuration JSON
                      <textarea
                        className="json-editor"
                        spellCheck={false}
                        rows={10}
                        value={configText}
                        onChange={(e) => setConfigText(e.target.value)}
                      />
                    </label>
                    {active.data.definition.type === "transform" && (
                      <p className="text-muted-foreground text-xs">
                        Each field accepts a literal value or an input JSON Pointer, for example
                        {" "}<code>{'{"kind":"input","pointer":"/ticket/id"}'}</code>.
                        The optional output schema checks the resulting object.
                      </p>
                    )}
                    {active.data.definition.type === "condition" && (
                      <p className="text-muted-foreground text-xs">
                        Compare literal values or input pointers. Both true and false paths must reach Return result; the selected path appears in the run trace.
                      </p>
                    )}
                    {active.data.definition.type === "text_template" && (
                      <p className="text-muted-foreground text-xs">Use placeholders such as <code>{"{{/ticket/id}}"}</code>. This node returns an object with a <code>text</code> field.</p>
                    )}
                    {active.data.definition.type === "list_filter" && (
                      <p className="text-muted-foreground text-xs">Select an array with <code>source</code>, compare each item with <code>item_pointer</code>, and receive <code>items</code> and <code>count</code>.</p>
                    )}
                    {active.data.definition.type === "json_parse" && (
                      <p className="text-muted-foreground text-xs">Select a JSON string with <code>source</code>. The parsed data is returned in <code>value</code>.</p>
                    )}
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => {
                        try {
                          const value = JSON.parse(configText);
                          if (
                            !value ||
                            typeof value !== "object" ||
                            Array.isArray(value)
                          )
                            throw new Error();
                          remember();
                          updateNode({ config: value });
                          setError("");
                        } catch {
                          setError(
                            "Node configuration must be a valid JSON object.",
                          );
                        }
                      }}
                    >
                      Apply configuration
                    </Button>
                    <div className="summary-divider" />
                    <label>
                      Connect to
                      <select
                        value={target}
                        onChange={(e) => setTarget(e.target.value)}
                      >
                        <option value="">Select a target step</option>
                        {nodes
                          .filter(
                            (n) =>
                              n.id !== selected &&
                              n.data.definition.type !== "manual_input",
                          )
                          .map((n) => (
                            <option key={n.id} value={n.id}>
                              {n.data.definition.label}
                            </option>
                          ))}
                      </select>
                    </label>
                    {active.data.definition.type === "condition" && (
                      <label>
                        Branch
                        <select
                          value={port}
                          onChange={(e) => setPort(e.target.value)}
                        >
                          <option value="true">True</option>
                          <option value="false">False</option>
                        </select>
                      </label>
                    )}
                    <Button
                      variant="outline"
                      size="sm"
                      disabled={
                        !target || active.data.definition.type === "result"
                      }
                      onClick={() => {
                        remember();
                        connect({
                          source: active.id,
                          target,
                          sourceHandle:
                            active.data.definition.type === "condition"
                              ? port === "false"
                                ? "false"
                                : "true"
                              : "out",
                          targetHandle: "in",
                        });
                        setTarget("");
                      }}
                    >
                      <Plus size={14} />
                      Add connection
                    </Button>
                  </>
                ) : (
                  <>
                    <label>
                      Step timeout (seconds)
                      <input
                        type="number"
                        min={1}
                        max={300}
                        value={String(
                          active.data.definition.policy.timeout_seconds || 60,
                        )}
                        onChange={(e) =>
                          updateNode({
                            policy: {
                              ...active.data.definition.policy,
                              timeout_seconds: Number(e.target.value),
                            },
                          })
                        }
                      />
                    </label>
                    <label>
                      Maximum attempts
                      <input
                        type="number"
                        min={1}
                        max={3}
                        value={String(
                          active.data.definition.policy.max_attempts || 1,
                        )}
                        onChange={(e) =>
                          updateNode({
                            policy: {
                              ...active.data.definition.policy,
                              max_attempts: Number(e.target.value),
                            },
                          })
                        }
                      />
                    </label>
                    <div className="permission-callout">
                      <ShieldCheck size={18} />
                      <p>
                        Retries will be allowed only for operations classified
                        as safe. Unknown external outcomes will not be replayed
                        automatically.
                      </p>
                    </div>
                  </>
                )}
                <Button variant="danger" size="sm" onClick={removeNode}>
                  <Trash2 size={14} />
                  Remove node
                </Button>
              </div>
            </>
          ) : (
            <div className="inspector-content">
              <div className="inspector-empty-icon">
                <WorkflowIcon size={27} />
              </div>
              <h3>Make your work flow</h3>
              <p className="muted">
                Select a node to configure its inputs, behavior and execution
                policies.
              </p>
              <div className="summary-divider" />
              <label>
                Workflow name
                <input
                  value={name}
                  maxLength={100}
                  onChange={(e) => setName(e.target.value)}
                />
              </label>
              <div className="summary-line">
                <span>Draft revision</span>
                <strong>{revision}</strong>
              </div>
              <div className="summary-line">
                <span>Execution timeout</span>
                <strong>{String(graph.limits.timeout_seconds)}s</strong>
              </div>
              <div className="summary-line">
                <span>Budget cap</span>
                <strong>${String(graph.limits.max_cost_usd)}</strong>
              </div>
              <div className="permission-callout">
                <ShieldCheck size={17} />
                <p>
                  Published runs support a single path with approved local tools
                  and one published agent with approved local tools. One condition can
                  route two paths that rejoin at the result. Data nodes reshape,
                  filter, parse, and compose values. Reviewed read-only MCP tools can run after an admin connects them.
                </p>
              </div>
            </div>
          )}
        </aside>
      </div>
      {panel && (
        <section className="validation-panel" aria-label="Workflow validation">
          <div className="validation-heading">
            <div className="row">
              <button className="active" onClick={() => setPanel(true)}>
                <ShieldCheck size={15} />
                Validation
              </button>
              {validation && (
                <Badge tone={validation.valid ? "green" : "amber"}>
                  {validation.errors.length} errors
                </Badge>
              )}
              <span className="muted">Structure and tool approval</span>
            </div>
            <button
              className="icon-button"
              onClick={() => setPanel(false)}
              aria-label="Collapse validation"
            >
              <X size={15} />
            </button>
          </div>
          <div className="validation-content">
            {!validation ? (
              <span className="validation-empty">
                <ShieldCheck size={17} />
                Validate your saved graph to find missing connections, loops and
                unavailable dependencies.
              </span>
            ) : validation.valid ? (
              <span className="validation-success">
                <Check size={18} />
                Structural checks passed for revision {validation.revision}.
                Published runs support linear paths with approved local tools.
              </span>
            ) : (
              validation.errors.map((e, i) => (
                <button
                  className="validation-error-row"
                  key={i}
                  onClick={() => {
                    if (e.node_id) selectNode(e.node_id);
                  }}
                >
                  <AlertCircle size={15} />
                  <code>{e.code}</code>
                  <span>{e.message}</span>
                  {e.node_id && (
                    <span className="error-node">
                      {e.node_id}
                      <ChevronRight size={12} />
                    </span>
                  )}
                </button>
              ))
            )}
          </div>
          <div className="workflow-preview-panel">
            <div>
              <strong>Draft preview</strong>
              <small>
                Runs locally approved tools against this saved draft. Agent steps
                require publishing and a durable run.
              </small>
            </div>
            <label htmlFor="workflow-preview-input">Input JSON</label>
            <textarea
              id="workflow-preview-input"
              className="run-input"
              spellCheck={false}
              value={previewInput}
              onChange={(event) => setPreviewInput(event.target.value)}
            />
            {previewResult && (
              <>
                <label htmlFor="workflow-preview-output">Output JSON</label>
                <pre id="workflow-preview-output">
                  {JSON.stringify(previewResult.output, null, 2)}
                </pre>
                <small>
                  {previewResult.steps
                    .map((step) => `${step.node_id}: ${step.status}`)
                    .join(" → ")}
                </small>
              </>
            )}
          </div>
          {publishedVersion && (
            <div className="workflow-preview-panel">
              <strong>Published version ready</strong>
              <small>
                Use Run to queue a durable execution. Version ID:{" "}
                {publishedVersion}
              </small>
              {durableRun && (
                <>
                  <p>
                    Run {durableRun.id}: <strong>{durableRun.state}</strong>
                    {durableRun.error_code && ` · ${durableRun.error_code}`}
                  </p>
                  {durableRun.output !== null && (
                    <pre>{JSON.stringify(durableRun.output, null, 2)}</pre>
                  )}
                  {durableRun.cost_usd && <small>Estimated model cost ${durableRun.cost_usd} · {durableRun.input_tokens} input / {durableRun.output_tokens} output tokens</small>}
                  {durableRun.uncertain_cost_usd && <small>Provider outcome uncertain; possible charge up to ${durableRun.uncertain_cost_usd}.</small>}
                  {durableRun.steps && (
                    <small>
                      {durableRun.steps
                        .map((step) => `${step.node_id}: ${step.status}`)
                        .join(" → ")}
                    </small>
                  )}
                </>
              )}
            </div>
          )}
        </section>
      )}
    </div>
  );
}
