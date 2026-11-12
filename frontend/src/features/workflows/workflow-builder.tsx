"use client";
import {
  createContext,
  memo,
  useCallback,
  useContext,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
} from "react";
import Link from "next/link";
import { LaunchChecklist } from "@/features/launch/launch-checklist";
import {
  deriveLaunchSteps,
  launchConfigKey,
  type SampleEvidence,
} from "@/features/launch/launch-model";
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
  useUpdateNodeInternals,
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
  MessageSquare,
  Sparkles,
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
  Repeat2,
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
import { SaveTemplate } from "@/features/templates/save-template";
import { Badge, ErrorNotice } from "@/components/shared/ui";
import { api } from "@/lib/api/client";
import { useUnsavedChanges } from "@/lib/use-unsaved-changes";
import {
  connectInsertedNode,
  edgesAfterConfigEdit,
  serializeEdges,
} from "./graph-edit";
import { PreviewSteps } from "./workflow-preview";
import {
  configSummary,
  outputPorts,
  inputFieldHints,
  issuesByNode,
  upstreamIds,
  type NodeIssues,
  requiresPublishedRun,
} from "./node-config";
import { NodeConfigForm, type FormContext } from "./node-config-forms";
import { NodeTestPanel, type NodeTestState } from "./node-test-panel";
import { DataMappings } from "./data-mappings";
import type {
  Connection as ProviderConnection,
  Graph,
  GraphNode,
  NodeKind,
  ToolOption,
  Validation,
  Workflow,
} from "@/lib/api/types";

type CanvasNode = Node<{ definition: GraphNode }, "flowforge">;
// Issues flow to canvas nodes through context so they never enter the saved graph definition.
const IssuesContext = createContext<{
  issues: NodeIssues;
  checked: boolean;
  toolNames: Record<string, string>;
}>({ issues: {}, checked: false, toolNames: {} });
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
    type: "chat_trigger",
    name: "Chat trigger",
    description: "Start from a chat message and keep the conversation going",
    icon: MessageSquare,
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
    type: "llm",
    name: "LLM",
    description: "Prompt a model here, with tools and APIs",
    icon: Sparkles,
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
    type: "switch",
    name: "Switch",
    description: "Route a value to a matching case or default",
    icon: GitBranch,
    tone: "amber",
    group: "LOGIC",
    enabled: true,
  },
  {
    type: "list_deduplicate",
    name: "Remove duplicates",
    description: "Keep the first occurrence of each list item",
    icon: ListFilter,
    tone: "blue",
    group: "DATA",
    enabled: true,
  },
  {
    type: "approval",
    name: "Human approval",
    description: "Pause for an owner or admin decision",
    icon: ShieldCheck,
    tone: "purple",
    group: "LOGIC",
    enabled: true,
  },
  {
    type: "wait",
    name: "Wait",
    description: "Resume later with a durable timer",
    icon: CircleDot,
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
    type: "merge",
    name: "Merge paths",
    description: "Wait for and combine connected paths",
    icon: GitBranch,
    tone: "amber",
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
    type: "subworkflow",
    name: "Subworkflow",
    description: "Reuse a published workflow version",
    icon: WorkflowIcon,
    tone: "purple",
    group: "LOGIC",
    enabled: true,
  },
  {
    type: "for_each",
    name: "For each item",
    description: "Run a workflow for each list item",
    icon: Repeat2,
    tone: "purple",
    group: "LOGIC",
    enabled: true,
  },
  {
    type: "http_tool",
    name: "HTTP API",
    description: "Read or write through an approved API",
    icon: PlugZap,
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
  const updateInternals = useUpdateNodeInternals();
  const portsKey = JSON.stringify(outputPorts(d));
  useEffect(() => {
    updateInternals(d.id);
  }, [d.id, portsKey, updateInternals]);
  const { issues: allIssues, checked, toolNames } = useContext(IssuesContext);
  const issues = allIssues[d.id] ?? [],
    errors = issues.filter((issue) => issue.severity === "error"),
    summary = configSummary(d, toolNames);
  const state = errors.length
    ? "error"
    : issues.length
      ? "warning"
      : checked
        ? "ready"
        : "draft";
  return (
    <div
      className={`flowforge-node ${selected ? "selected" : ""} ${state === "error" ? "has-errors" : ""}`}
    >
      <div className="flow-node-top">
        <span className={`node-icon ${kind.tone}`}>
          <Icon size={19} />
        </span>
        <span className="flow-node-category">{kind.name.toUpperCase()}</span>
        <MoreHorizontal size={15} />
      </div>
      <strong>{d.label}</strong>
      <p className={summary ? "flow-node-summary" : undefined}>
        {summary ??
          (d.type === "agent"
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
                              : d.type === "chat_trigger"
                                ? "Receive a chat message"
                                : "Provide workflow input")}
      </p>
      <div className={`flow-node-footer ${state}`} title={issues[0]?.message}>
        <span className="node-state-dot" />
        {state === "error"
          ? `${errors.length} ${errors.length === 1 ? "issue" : "issues"} to fix`
          : state === "warning"
            ? `${issues.length} ${issues.length === 1 ? "warning" : "warnings"}`
            : state === "ready"
              ? "Configured"
              : "Draft configuration"}
        {d.type === "agent" && <LockKeyhole size={11} />}
      </div>
      {d.type !== "manual_input" &&
        d.type !== "webhook_trigger" &&
        d.type !== "schedule_trigger" &&
        d.type !== "chat_trigger" && (
          <Handle type="target" position={Position.Left} id="in" />
        )}
      {d.type === "switch" && (
        <div className="flow-switch-ports">
          {outputPorts(d).map((port) => (
            <div className="flow-switch-port" key={port.id}>
              <span>
                {port.label} <code>({port.id})</code>
              </span>
              <Handle
                type="source"
                position={Position.Right}
                id={port.id}
                aria-label={`${port.label} output (${port.id})`}
              />
            </div>
          ))}
        </div>
      )}
      {d.type !== "result" &&
        d.type !== "switch" &&
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

export function WorkflowBuilder({
  workflow,
  agentOptions,
  mcpOptions,
  httpOptions,
  workflowOptions: initialWorkflowOptions,
  toolOptions,
  connections,
  skillOptions = [],
  initialPublishedVersion,
  canEdit = true,
}: {
  workflow: Workflow;
  agentOptions: FormContext["agentOptions"];
  mcpOptions: FormContext["mcpOptions"];
  httpOptions: FormContext["httpOptions"];
  workflowOptions: FormContext["workflowOptions"];
  toolOptions: ToolOption[];
  connections: ProviderConnection[];
  skillOptions?: FormContext["skillOptions"];
  initialPublishedVersion: string | null;
  canEdit?: boolean;
}) {
  const preferredConnection = connections.find(
    (item) => item.state === "active" && item.default_model_id,
  );
  const [workflowOptions, setWorkflowOptions] = useState(
    initialWorkflowOptions,
  );
  const [loadingWorkflows, setLoadingWorkflows] = useState(false);
  const [nodes, setNodes, onNodesChange] = useNodesState<CanvasNode>(
      canvasNodes(workflow.graph),
    ),
    [edges, setEdges, onEdgesChange] = useEdgesState(
      canvasEdges(workflow.graph),
    );
  const [name, setName] = useState(workflow.name),
    [revision, setRevision] = useState(workflow.revision),
    [selected, setSelected] = useState<string | null>(
      workflow.graph.nodes.find((node) =>
        [
          "manual_input",
          "webhook_trigger",
          "schedule_trigger",
          "chat_trigger",
        ].includes(node.type),
      )?.id || null,
    ),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [validation, setValidation] = useState<Validation | null>(null),
    [panel, setPanel] = useState(true),
    [query, setQuery] = useState(""),
    [inspectorTab, setInspectorTab] = useState("configuration"),
    [configText, setConfigText] = useState(
      JSON.stringify(
        workflow.graph.nodes.find((node) =>
          [
            "manual_input",
            "webhook_trigger",
            "schedule_trigger",
            "chat_trigger",
          ].includes(node.type),
        )?.config || {},
        null,
        2,
      ),
    ),
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
    steps: {
      node_id: string;
      type: string;
      status: string;
      output: unknown;
      selected_port?: string | null;
    }[];
  } | null>(null);
  const [publishedVersion, setPublishedVersion] = useState<string | null>(
    initialPublishedVersion,
  );
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
    edges: serializeEdges(edges),
  };
  const snapshot = JSON.stringify({ name, graph }),
    [baseline, setBaseline] = useState(snapshot),
    dirty = snapshot !== baseline;
  useUnsavedChanges(dirty);
  const configKey = launchConfigKey({ name, graph });
  const currentKey = useRef(configKey);
  const configGeneration = useRef(0);
  useLayoutEffect(() => {
    if (currentKey.current !== configKey) configGeneration.current++;
    currentKey.current = configKey;
  }, [configKey]);
  const [checkedKey, setCheckedKey] = useState<string | null>(null);
  const [checkedValidation, setCheckedValidation] = useState<Validation | null>(
    null,
  );
  const [checking, setChecking] = useState(false);
  const [sample, setSample] = useState<SampleEvidence | null>(null);
  const latestRequest = useRef<string | null>(null);
  const [evidenceKey, setEvidenceKey] = useState(configKey);
  if (evidenceKey !== configKey) {
    setEvidenceKey(configKey);
    setCheckedKey(null);
    setSample(null);
  }
  useLayoutEffect(() => {
    latestRequest.current = null;
  }, [configKey]);
  useEffect(() => {
    let hidden = document.visibilityState === "hidden";
    const visibility = () => {
      if (document.visibilityState === "hidden") hidden = true;
      else if (hidden) {
        hidden = false;
        configGeneration.current++;
        latestRequest.current = null;
        setCheckedKey(null);
        setSample(null);
      }
    };
    document.addEventListener("visibilitychange", visibility);
    return () => document.removeEventListener("visibilitychange", visibility);
  }, []);
  function startSample(mode: SampleEvidence["mode"], versionId?: string) {
    const evidence: SampleEvidence = {
      requestId: crypto.randomUUID(),
      configKey,
      inputKey: launchConfigKey(previewInput),
      mode,
      state: "running",
      versionId,
    };
    latestRequest.current = evidence.requestId;
    setSample(evidence);
    return evidence;
  }
  function finishSample(
    evidence: SampleEvidence,
    state: SampleEvidence["state"],
    runId?: string,
  ) {
    if (
      latestRequest.current === evidence.requestId &&
      currentKey.current === evidence.configKey
    )
      setSample({ ...evidence, state, runId });
  }
  function showSample() {
    setPanel(true);
    setTimeout(
      () => document.getElementById("workflow-preview-input")?.focus(),
      0,
    );
  }
  const active = nodes.find((n) => n.id === selected),
    activeKind = kinds.find((k) => k.type === active?.data.definition.type);
  // Positions never affect validity, so dragging does not trigger a check.
  const checkKey = JSON.stringify({
    ...graph,
    nodes: graph.nodes.map(({ position: _position, ...rest }) => rest),
  });
  const checkSeq = useRef(0);
  const [checkError, setCheckError] = useState("");
  const [tests, setTests] = useState<Record<string, NodeTestState>>({});
  const setTest = useCallback((nodeId: string, update: NodeTestState) => {
    setTests((current) => ({
      ...current,
      [nodeId]: { ...current[nodeId], ...update },
    }));
  }, []);
  useEffect(() => {
    const seq = ++checkSeq.current;
    const timer = setTimeout(async () => {
      const draft = JSON.parse(checkKey) as Omit<Graph, "nodes"> & {
        nodes: Omit<GraphNode, "position">[];
      };
      try {
        const result = await api<Validation>(
          `/workspaces/${workflow.workspace_id}/workflows/${workflow.id}/check`,
          {
            method: "POST",
            body: JSON.stringify({
              graph: {
                ...draft,
                nodes: draft.nodes.map((node) => ({
                  ...node,
                  position: { x: 0, y: 0 },
                })),
              },
            }),
          },
        );
        if (seq !== checkSeq.current) return;
        setValidation(result);
        setCheckError("");
      } catch (cause) {
        if (seq === checkSeq.current)
          setCheckError(
            cause instanceof Error ? cause.message : "Live check unavailable.",
          );
      }
    }, 600);
    return () => clearTimeout(timer);
  }, [checkKey, workflow.workspace_id, workflow.id, workflowOptions]);
  const nodeIssues = issuesByNode(validation),
    activeIssues = (active && nodeIssues[active.id]) || [],
    blockingErrors = validation?.errors.length ?? 0,
    blockedTitle = blockingErrors
      ? `Fix ${blockingErrors} ${blockingErrors === 1 ? "issue" : "issues"} first. Drafts can still be saved.`
      : "";
  const toolNames = Object.fromEntries([
    ...toolOptions.map((tool) => [tool.key, tool.name]),
    ...workflowOptions.map((option) => [
      option.id,
      `${option.name} v${option.number}`,
    ]),
  ]);
  const needsPublishedRun = requiresPublishedRun(graph.nodes, workflowOptions);
  const activeConfig = active?.data.definition.config ?? {},
    activeAgent = agentOptions.find(
      (option) => option.id === activeConfig.version_id,
    ),
    externalTarget =
      active?.data.definition.type === "llm"
        ? `${String(activeConfig.provider)}/${String(activeConfig.model_id || "a model")}`
        : active?.data.definition.type === "agent"
          ? activeAgent
            ? `the agent “${activeAgent.name}” v${activeAgent.number} on ${activeAgent.provider}/${activeAgent.model_id}`
            : "a published agent"
          : active?.data.definition.type === "mcp_tool"
            ? `${mcpOptions.find((server) => server.id === activeConfig.server_id)?.name ?? String(activeConfig.server_id)} · ${String(activeConfig.tool_name)}`
            : active?.data.definition.type === "http_tool"
              ? (httpOptions.find((tool) => tool.id === activeConfig.tool_id)
                  ?.url ?? "an approved HTTP API")
              : null,
    testBlocked =
      activeIssues.find(
        (issue) =>
          issue.severity === "error" &&
          (issue.path?.startsWith("config") ||
            issue.path?.startsWith("policy.")),
      )?.message ?? null;
  const formContext: FormContext = {
    workspaceId: workflow.workspace_id,
    workflowId: workflow.id,
    nodes: graph.nodes,
    upstream: active ? upstreamIds(graph.edges, active.id) : [],
    inputHints: inputFieldHints(graph.input_schema),
    agentOptions,
    mcpOptions,
    httpOptions,
    workflowOptions,
    refreshWorkflows,
    loadingWorkflows,
    toolOptions,
    connections,
    skillOptions,
  };
  async function refreshWorkflows() {
    setLoadingWorkflows(true);
    setError("");
    try {
      const result = await api<{ items: FormContext["workflowOptions"] }>(
        `/workspaces/${workflow.workspace_id}/workflows/call-options?exclude_workflow_id=${workflow.id}`,
      );
      setWorkflowOptions(result.items);
    } catch (cause) {
      setError(
        cause instanceof Error
          ? cause.message
          : "Could not refresh published workflows.",
      );
    } finally {
      setLoadingWorkflows(false);
    }
  }
  function remember() {
    setHistory((h) => [...h.slice(-29), structuredClone(graph)]);
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
    if (type === "result" && nodes.some((n) => n.data.definition.type === type))
      return;
    if (
      [
        "manual_input",
        "webhook_trigger",
        "schedule_trigger",
        "chat_trigger",
      ].includes(type) &&
      nodes.some((n) =>
        [
          "manual_input",
          "webhook_trigger",
          "schedule_trigger",
          "chat_trigger",
        ].includes(n.data.definition.type),
      )
    ) {
      setError(
        "A workflow can have one trigger. Remove the existing trigger first.",
      );
      return;
    }
    if (
      type === "condition" &&
      nodes.some((n) => n.data.definition.type === "condition")
    ) {
      setError("Published workflows currently support one condition node.");
      return;
    }
    remember();
    const kind = kinds.find((k) => k.type === type)!;
    const id = `${type}-${crypto.randomUUID().slice(0, 8)}`;
    const selectedNode = nodes.find((n) => n.id === selected);
    const source =
      selectedNode?.data.definition.type === "result"
        ? nodes.find(
            (n) =>
              n.id ===
              edges.find((edge) => edge.target === selectedNode.id)?.source,
          )
        : selectedNode;
    const sourcePorts = source ? outputPorts(source.data.definition) : [];
    const branchPort =
      sourcePorts.find((item) => item.id === port)?.id ??
      sourcePorts[0]?.id ??
      "out";
    const outgoing = source
      ? edges.filter(
          (edge) =>
            edge.source === source.id && edge.sourceHandle === branchPort,
        )
      : [];
    const next =
      outgoing.length === 1
        ? nodes.find((n) => n.id === outgoing[0].target)
        : undefined;
    const config: Record<string, unknown> =
      type === "switch"
        ? {
            value: { kind: "input", pointer: "" },
            cases: [
              {
                id: `case_${crypto.randomUUID().slice(0, 8)}`,
                label: "Case 1",
                value: "match",
              },
            ],
          }
        : type === "list_deduplicate"
          ? { source: "/items" }
          : type === "approval"
            ? {
                prompt: "Review the input before continuing.",
                expires_seconds: 3600,
                allow_requester: false,
              }
            : type === "wait"
              ? { seconds: 60 }
              : type === "condition"
                ? {
                    operator: "eq",
                    left: { kind: "literal", value: true },
                    right: { kind: "literal", value: true },
                  }
                : type === "agent"
                  ? { version_id: "" }
                  : type === "llm"
                    ? {
                        instructions: "",
                        provider: preferredConnection?.provider ?? "openai",
                        model_id: preferredConnection?.default_model_id ?? "",
                        tool_keys: [],
                        mcp_tools: [],
                        http_tools: [],
                      }
                    : type === "subworkflow"
                      ? { version_id: "" }
                      : type === "for_each"
                        ? {
                            version_id: "",
                            source: "/items",
                            max_items: 3,
                            input_mode: "envelope",
                          }
                        : type === "transform"
                          ? {
                              fields: {
                                message: { kind: "literal", value: "" },
                              },
                              output_schema: {
                                type: "object",
                                properties: { message: { type: "string" } },
                              },
                            }
                          : type === "merge"
                            ? { mode: "active" }
                            : type === "text_template"
                              ? { template: "Ticket {{/ticket/id}} is ready." }
                              : type === "list_filter"
                                ? {
                                    source: "/items",
                                    item_pointer: "/status",
                                    operator: "eq",
                                    value: "open",
                                  }
                                : type === "json_parse"
                                  ? { source: "/text" }
                                  : type === "tool"
                                    ? { tool_key: "text.replace" }
                                    : type === "http_tool"
                                      ? {
                                          tool_id:
                                            httpOptions.find(
                                              (option) =>
                                                option.state === "active",
                                            )?.id || "",
                                        }
                                      : type === "mcp_tool"
                                        ? {
                                            server_id:
                                              mcpOptions.find(
                                                (option) =>
                                                  option.runnable_tools.length,
                                              )?.id || "",
                                            tool_name:
                                              mcpOptions.find(
                                                (option) =>
                                                  option.runnable_tools.length,
                                              )?.runnable_tools[0] || "",
                                          }
                                        : type === "result"
                                          ? {
                                              value: {
                                                kind: "output",
                                                node_id: "input",
                                                pointer: "",
                                              },
                                            }
                                          : {};
    const definition: GraphNode = {
      id,
      type,
      label: kind.name,
      config,
      position: {
        x: source
          ? next
            ? (source.position.x + next.position.x) / 2
            : source.position.x + 280
          : 240 + (nodes.length % 3) * 100,
        y: source
          ? next
            ? (source.position.y + next.position.y) / 2 + 80
            : source.position.y + 120
          : 100 + nodes.length * 60,
      },
      join: "all",
      policy: { timeout_seconds: 60, max_attempts: 1 },
    };
    const insertsSwitch = type === "switch" && outgoing.length === 1 && !!next;
    const hasOtherPredecessors =
      !!next &&
      edges.some(
        (edge) => edge.target === next.id && edge.id !== outgoing[0]?.id,
      );
    const continuationRequiresAll =
      next &&
      next.data.definition.type !== "result" &&
      (next.data.definition.type === "merge"
        ? next.data.definition.config.mode === "all"
        : next.data.definition.join === "all");
    // Collapse the exclusive routes before a shared all-join, retaining its other prerequisites.
    const continuationMerge: GraphNode | undefined =
      insertsSwitch &&
      continuationRequiresAll &&
      (hasOtherPredecessors || next.data.definition.type === "merge")
        ? {
            id: `merge-${crypto.randomUUID().slice(0, 8)}`,
            type: "merge",
            label: "Merge paths",
            config: { mode: "active" },
            join: "active",
            position: {
              x: (definition.position.x + next.position.x) / 2,
              y: next.position.y + 80,
            },
            policy: { timeout_seconds: 60, max_attempts: 1 },
          }
        : undefined;
    setNodes((n) => [
      ...n.map((existing) =>
        next?.id === existing.id && existing.data.definition.type === "result"
          ? {
              ...existing,
              data: {
                definition: {
                  ...existing.data.definition,
                  config:
                    ["condition", "switch"].includes(type) ||
                    edges.filter((edge) => edge.target === next?.id).length > 1
                      ? {}
                      : { value: { kind: "output", node_id: id, pointer: "" } },
                },
              },
            }
          : next?.id === existing.id &&
              insertsSwitch &&
              !hasOtherPredecessors &&
              !continuationMerge
            ? {
                ...existing,
                data: {
                  definition: {
                    ...existing.data.definition,
                    join: "active" as const,
                  },
                },
              }
            : existing,
      ),
      {
        id,
        type: "flowforge",
        position: definition.position,
        data: { definition },
      },
      ...(continuationMerge
        ? [
            {
              id: continuationMerge.id,
              type: "flowforge" as const,
              position: continuationMerge.position,
              data: { definition: continuationMerge },
            },
          ]
        : []),
    ]);
    if (source && source.data.definition.type !== "result") {
      if (outgoing.length === 1 && next) {
        if (["condition", "switch"].includes(type)) {
          setEdges((current) => [
            ...current.map((edge) =>
              edge.id === outgoing[0].id ? { ...edge, target: id } : edge,
            ),
            ...outputPorts(definition).map(({ id: branch }) => ({
              id: `edge-${crypto.randomUUID()}`,
              source: id,
              target: continuationMerge?.id ?? next.id,
              sourceHandle: branch,
              targetHandle: "in",
              type: "smoothstep" as const,
              data: { mappings: [] },
            })),
            ...(continuationMerge
              ? [
                  {
                    id: `edge-${crypto.randomUUID()}`,
                    source: continuationMerge.id,
                    target: next.id,
                    sourceHandle: "out",
                    targetHandle: "in",
                    type: "smoothstep",
                    data: { mappings: [] },
                  },
                ]
              : []),
          ]);
        } else {
          setEdges((current) =>
            connectInsertedNode(
              current,
              source.id,
              id,
              outgoing[0],
              `edge-${crypto.randomUUID()}`,
            ),
          );
        }
      } else if (outgoing.length === 0) {
        setEdges((current) => [
          ...current,
          {
            id: `edge-${crypto.randomUUID()}`,
            source: source.id,
            target: id,
            sourceHandle: branchPort,
            targetHandle: "in",
            type: "smoothstep",
            data: { mappings: [] },
          },
        ]);
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
    },
    [setEdges],
  );
  function updateNode(update: Partial<GraphNode>) {
    if (active && update.config)
      setEdges((current) =>
        edgesAfterConfigEdit(current, active.data.definition, update.config!),
      );
    setNodes((ns) =>
      ns.map((n) =>
        n.id === selected
          ? { ...n, data: { definition: { ...n.data.definition, ...update } } }
          : n,
      ),
    );
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
  }
  async function save(): Promise<Workflow | null> {
    if (!canEdit) return null;
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
    if (!canEdit) return;
    const submittedKey = configKey;
    const submittedGeneration = configGeneration.current;
    setPanel(true);
    let currentRevision = revision;
    if (dirty) {
      const saved = await save();
      if (!saved) return;
      currentRevision = saved.revision;
    }
    setCheckedKey(null);
    setChecking(true);
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
      if (
        currentKey.current === submittedKey &&
        configGeneration.current === submittedGeneration
      ) {
        setValidation(result);
        setCheckedValidation(result);
        setCheckedKey(submittedKey);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Validation unavailable.");
    } finally {
      setChecking(false);
      setBusy(false);
    }
  }
  async function preview() {
    if (!canEdit) return;
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
    const evidence = startSample("local_preview");
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
          selected_port?: string | null;
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
      if (
        currentKey.current === evidence.configKey &&
        latestRequest.current === evidence.requestId
      )
        setPreviewResult(result);
      finishSample(evidence, "completed");
    } catch (cause) {
      finishSample(evidence, "failed");
      setError(
        cause instanceof Error ? cause.message : "Preview could not run.",
      );
    } finally {
      setBusy(false);
    }
  }
  async function publish() {
    if (!canEdit) return;
    const submittedKey = configKey;
    const submittedGeneration = configGeneration.current;
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
      if (
        currentKey.current !== submittedKey ||
        configGeneration.current !== submittedGeneration
      )
        return;
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
    if (!canEdit || !publishedVersion || dirty) return;
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
    const evidence = startSample("published_run", publishedVersion);
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
      if (
        currentKey.current === evidence.configKey &&
        latestRequest.current === evidence.requestId
      )
        setDurableRun(run);
      for (
        let i = 0;
        i < 35 && (run.state === "queued" || run.state === "running");
        i++
      ) {
        await new Promise((resolve) => setTimeout(resolve, 1000));
        run = await api<typeof run>(`${path}/${run.id}`);
        if (
          currentKey.current === evidence.configKey &&
          latestRequest.current === evidence.requestId
        )
          setDurableRun(run);
      }
      finishSample(
        evidence,
        run.state === "completed"
          ? "completed"
          : ["waiting", "pending_approval"].includes(run.state)
            ? "waiting"
            : run.state === "failed"
              ? "failed"
              : run.state === "cancelled"
                ? "cancelled"
                : "unknown",
        run.id,
      );
    } catch (cause) {
      finishSample(evidence, "failed");
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
          {nodes.some(
            (node) => node.data.definition.type === "chat_trigger",
          ) && (
            <Button asChild variant="outline" size="sm">
              <Link
                href={`/w/${workflow.workspace_id}/workflows/${workflow.id}/chat`}
                title="Chat with the latest published version"
              >
                <MessageSquare size={14} />
                Chat
              </Link>
            </Button>
          )}
          <SaveTemplate
            workspaceId={workflow.workspace_id}
            sourceId={workflow.id}
            kind="workflow"
            revision={revision}
            name={name}
            description={workflow.description}
            disabled={busy || dirty}
          />
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
            disabled={!canEdit || busy || !dirty}
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
            disabled={!canEdit || busy}
          >
            <ShieldCheck size={15} />
            {dirty ? "Save & validate" : "Validate"}
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={preview}
            disabled={
              !canEdit || busy || blockingErrors > 0 || needsPublishedRun
            }
            title={
              blockedTitle ||
              (needsPublishedRun
                ? "External steps require a published workflow run. Publish and use Run."
                : "Preview local steps without creating a run.")
            }
          >
            <Play size={14} />
            Preview
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={publish}
            disabled={!canEdit || busy || blockingErrors > 0}
            title={
              blockedTitle ||
              "Publish a validated workflow with up to 30 steps and four agent nodes."
            }
          >
            <LockKeyhole size={13} />
            Publish
          </Button>
          <Button
            size="sm"
            onClick={runPublished}
            disabled={!canEdit || busy || !publishedVersion || dirty}
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
      <LaunchChecklist
        steps={deriveLaunchSteps({
          mode: needsPublishedRun ? "published_run" : "local_preview",
          saved: true,
          dirty,
          canEdit,
          configKey,
          latestRequestId: sample?.requestId ?? null,
          check: checking
            ? "checking"
            : checkedKey === configKey
              ? checkedValidation?.valid
                ? "passed"
                : "blocked"
              : "unchecked",
          issues:
            checkedKey === configKey
              ? (checkedValidation?.errors ?? []).map((issue) => ({
                  code: issue.code,
                  message: issue.message,
                  target: issue.node_id ?? undefined,
                }))
              : [],
          warnings: [],
          publishedCurrent: !!publishedVersion && !dirty,
          publishedVersionId: publishedVersion,
          sample,
        })}
        issues={
          checkedKey === configKey
            ? (checkedValidation?.errors ?? []).map((issue) => ({
                code: issue.code,
                message: issue.message,
                target: issue.node_id ?? undefined,
              }))
            : []
        }
        warnings={
          checkedKey === configKey
            ? (checkedValidation?.warnings ?? []).map((issue) => ({
                code: issue.code,
                message: issue.message,
              }))
            : []
        }
        canEdit={canEdit}
        onAction={(action) => {
          if (busy) return;
          if (action === "save") void save();
          else if (action === "check") void validate();
          else if (action === "publish") void publish();
          else showSample();
        }}
        onIssue={(issue) => {
          setPanel(true);
          if (issue.target && nodes.some((node) => node.id === issue.target)) {
            selectNode(issue.target);
            setListView(true);
          } else
            setTimeout(
              () =>
                document
                  .querySelector<HTMLElement>(
                    '[aria-label="Workflow validation"]',
                  )
                  ?.focus(),
              0,
            );
        }}
      />
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
          <p className="palette-guidance">
            Select a step, then click a node to add a connected step. No
            dragging needed. Save, validate and preview when ready.
          </p>
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
                    disabled={
                      !k.enabled ||
                      ((k.type === "manual_input" || k.type === "result") &&
                        nodes.some((n) => n.data.definition.type === k.type))
                    }
                    onClick={() => addNode(k.type)}
                    title={
                      k.enabled
                        ? `Add ${k.name}${selected ? " after the selected step" : ""}`
                        : k.description
                    }
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
                        {nodeIssues[n.id]?.some(
                          (issue) => issue.severity === "error",
                        ) && (
                          <>
                            {" "}
                            ·{" "}
                            <span className="field-error">
                              {
                                nodeIssues[n.id].filter(
                                  (issue) => issue.severity === "error",
                                ).length
                              }{" "}
                              to fix
                            </span>
                          </>
                        )}
                      </span>
                    </div>
                    <ChevronRight size={16} />
                  </button>
                ))}
              </div>
            ) : (
              <IssuesContext.Provider
                value={{
                  issues: nodeIssues,
                  checked: validation !== null,
                  toolNames,
                }}
              >
                <ReactFlow
                  nodes={nodes}
                  edges={edges.map((edge) => {
                    const source = graph.nodes.find(
                      (node) => node.id === edge.source,
                    );
                    const label =
                      source?.type === "switch"
                        ? outputPorts(source).find(
                            (item) => item.id === edge.sourceHandle,
                          )?.label
                        : undefined;
                    return label
                      ? { ...edge, label: `${label} (${edge.sourceHandle})` }
                      : edge;
                  })}
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
              </IssuesContext.Provider>
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
              <div className="inspector-tabs" role="tablist">
                {(
                  [
                    ["configuration", "Configuration"],
                    ["test", "Test"],
                    ["advanced", "Advanced JSON"],
                    ["policy", "Policies"],
                  ] as const
                ).map(([tab, title]) => (
                  <button
                    key={tab}
                    role="tab"
                    aria-selected={inspectorTab === tab}
                    className={inspectorTab === tab ? "active" : ""}
                    onClick={() => {
                      if (tab === "advanced")
                        setConfigText(
                          JSON.stringify(
                            active.data.definition.config,
                            null,
                            2,
                          ),
                        );
                      setInspectorTab(tab);
                    }}
                  >
                    {title}
                    {tab === "configuration" &&
                      activeIssues.some(
                        (issue) => issue.severity === "error",
                      ) && (
                        <span
                          className="tab-issue-dot"
                          aria-label="has issues"
                        />
                      )}
                  </button>
                ))}
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
                      {!active.data.definition.label.trim() && (
                        <span className="field-error">
                          Give this step a name so the draft can be saved.
                        </span>
                      )}
                    </label>
                    {graph.edges.filter((edge) => edge.target === active.id)
                      .length > 1 &&
                      active.data.definition.type !== "merge" &&
                      active.data.definition.type !== "result" && (
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
                            <option value="all">
                              All paths must be active
                            </option>
                            <option value="active">Merge active paths</option>
                          </select>
                        </label>
                      )}
                    <div className="summary-divider" />
                    {/* One undo entry per focused field, not per keystroke. */}
                    <div onFocus={remember}>
                      <NodeConfigForm
                        key={active.id}
                        node={active.data.definition}
                        issues={activeIssues}
                        context={formContext}
                        onChange={(config) => updateNode({ config })}
                      />
                    </div>
                    <DataMappings
                      incoming={graph.edges.filter(
                        (edge) => edge.target === active.id,
                      )}
                      names={Object.fromEntries(
                        graph.nodes.map((node) => [node.id, node.label]),
                      )}
                      issues={validation?.errors || []}
                      remember={remember}
                      onChange={(id, mappings) =>
                        setEdges((current) =>
                          current.map((edge) =>
                            edge.id === id
                              ? { ...edge, data: { ...edge.data, mappings } }
                              : edge,
                          ),
                        )
                      }
                    />
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
                    {["condition", "switch"].includes(
                      active.data.definition.type,
                    ) && (
                      <label>
                        Branch
                        <select
                          value={
                            outputPorts(active.data.definition).some(
                              (item) => item.id === port,
                            )
                              ? port
                              : outputPorts(active.data.definition)[0]?.id
                          }
                          onChange={(e) => setPort(e.target.value)}
                        >
                          {outputPorts(active.data.definition).map((item) => (
                            <option key={item.id} value={item.id}>
                              {item.label} ({item.id})
                            </option>
                          ))}
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
                            outputPorts(active.data.definition).find(
                              (item) => item.id === port,
                            )?.id ??
                            outputPorts(active.data.definition)[0]?.id ??
                            "out",
                          targetHandle: "in",
                        });
                        setTarget("");
                      }}
                    >
                      <Plus size={14} />
                      Add connection
                    </Button>
                  </>
                ) : inspectorTab === "test" ? (
                  <NodeTestPanel
                    key={active.id}
                    workspaceId={workflow.workspace_id}
                    workflowId={workflow.id}
                    graph={graph}
                    node={active.data.definition}
                    tests={tests}
                    setTest={setTest}
                    sampleInput={previewInput}
                    blocked={
                      ["approval", "wait"].includes(active.data.definition.type)
                        ? "Publish and run this workflow to create a durable decision or timer. Open Workflow executions to review it."
                        : testBlocked
                          ? `Fix this step's settings first: ${testBlocked}`
                          : active.data.definition.type === "http_tool" &&
                              !httpOptions.find(
                                (tool) => tool.id === activeConfig.tool_id,
                              )?.read_only
                            ? "Use a published workflow run to execute this action and retain its receipt."
                            : ["subworkflow", "for_each"].includes(
                                  active.data.definition.type,
                                ) &&
                                requiresPublishedRun(
                                  [active.data.definition],
                                  workflowOptions,
                                )
                              ? "Use a published run for nested external steps, decisions and timers so progress and recovery are retained."
                              : null
                    }
                    externalTarget={externalTarget}
                  />
                ) : inspectorTab === "advanced" ? (
                  <>
                    <label>
                      Configuration JSON
                      <textarea
                        className="json-editor"
                        spellCheck={false}
                        rows={14}
                        value={configText}
                        onChange={(e) => setConfigText(e.target.value)}
                      />
                    </label>
                    <p className="node-form-hint">
                      Applied JSON is checked against the same rules as the
                      form. Issues below update after each change.
                    </p>
                    <div className="row">
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
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() =>
                          setConfigText(
                            JSON.stringify(
                              active.data.definition.config,
                              null,
                              2,
                            ),
                          )
                        }
                      >
                        Reset
                      </Button>
                    </div>
                    {activeIssues.length > 0 && (
                      <ul className="node-field-issues">
                        {activeIssues.map((issue, index) => (
                          <li key={index} className={issue.severity}>
                            <AlertCircle size={11} />
                            {issue.path && <code>{issue.path}</code>}
                            {issue.message}
                          </li>
                        ))}
                      </ul>
                    )}
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
                        max={
                          [
                            "agent",
                            "mcp_tool",
                            "http_tool",
                            "subworkflow",
                            "for_each",
                            "approval",
                            "wait",
                          ].includes(active.data.definition.type)
                            ? 1
                            : 3
                        }
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
                        Local steps retry only temporary availability errors or
                        timeouts. Input and contract failures stop immediately.
                        External steps, workflow calls and loops use one
                        attempt. Completed child receipts are reused during safe
                        recovery; replay starts a new run and can repeat
                        external actions.
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
                <strong>
                  {Math.min(
                    Number(graph.limits.timeout_seconds || 60),
                    needsPublishedRun ? 30 : 15,
                  )}
                  s effective
                </strong>
              </div>
              <div className="summary-line">
                <span>Budget cap</span>
                <strong>${String(graph.limits.max_cost_usd)}</strong>
              </div>
              <div className="summary-line">
                <span>Worst-case expanded steps</span>
                <strong>{validation?.expanded_steps ?? "—"} / 120</strong>
              </div>
              <div className="summary-line">
                <span>Worst-case agent calls</span>
                <strong>{validation?.agent_steps ?? "—"} / 8</strong>
              </div>
              <div className="permission-callout">
                <ShieldCheck size={17} />
                <p>
                  Published workflows support up to 30 steps and four agent
                  nodes, nested conditions, fan-out and merge paths. Loops call
                  a published workflow for up to 20 items, with at most three
                  workflow levels and 120 expanded steps. Steps execute in a
                  deterministic sequence within one shared workflow budget and
                  deadline. Multiple active inputs are grouped by source step
                  ID. Select a step to map incoming fields. Reviewed read-only
                  MCP tools require an admin connection.
                </p>
              </div>
            </div>
          )}
        </aside>
      </div>
      {panel && (
        <section
          className="validation-panel"
          aria-label="Workflow validation"
          tabIndex={-1}
        >
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
              <span className="muted">
                {validation?.revision
                  ? `Saved revision ${validation.revision}`
                  : "Live check of this draft"}{" "}
                · structure, configuration and tool approval
              </span>
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
            {checkError && (
              <span className="validation-empty">
                <AlertCircle size={17} />
                Live check paused: {checkError}
              </span>
            )}
            {!validation ? (
              <span className="validation-empty">
                <ShieldCheck size={17} />
                Checking this draft for missing settings, connections, loops and
                unavailable dependencies…
              </span>
            ) : validation.valid ? (
              <span className="validation-success">
                <Check size={18} />
                {validation.revision
                  ? `All checks passed for revision ${validation.revision}.`
                  : "All checks passed for this draft."}
                {validation.publishable
                  ? " Ready to preview and publish."
                  : " Review the reported configuration, dependency and expanded-work limits before publishing."}
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
                      {nodes.find((n) => n.id === e.node_id)?.data.definition
                        .label ?? e.node_id}
                      <ChevronRight size={12} />
                    </span>
                  )}
                </button>
              ))
            )}
            {validation &&
              validation.warnings.map((e, i) => (
                <button
                  className="validation-error-row warning"
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
                      {nodes.find((n) => n.id === e.node_id)?.data.definition
                        .label ?? e.node_id}
                      <ChevronRight size={12} />
                    </span>
                  )}
                </button>
              ))}
          </div>
          <div className="workflow-preview-panel">
            <div>
              <strong>Draft preview</strong>
              <small>
                Runs locally approved tools against this saved draft. Agent
                steps require publishing and a durable run.
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
                <PreviewSteps nodes={graph.nodes} steps={previewResult.steps} />
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
                  <Link
                    className="text-link"
                    href={`/w/${workflow.workspace_id}/executions?kind=workflows&runId=${durableRun.id}`}
                  >
                    Open durable step debugger
                  </Link>
                  {durableRun.output !== null && (
                    <pre>{JSON.stringify(durableRun.output, null, 2)}</pre>
                  )}
                  {durableRun.cost_usd && (
                    <small>
                      Estimated model cost ${durableRun.cost_usd} ·{" "}
                      {durableRun.input_tokens} input /{" "}
                      {durableRun.output_tokens} output tokens
                    </small>
                  )}
                  {durableRun.uncertain_cost_usd && (
                    <small>
                      Provider outcome uncertain; possible charge up to $
                      {durableRun.uncertain_cost_usd}.
                    </small>
                  )}
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
