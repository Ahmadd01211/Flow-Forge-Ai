import type { GraphNode, Validation, ValidationIssue } from "@/lib/api/types";

export function requiresPublishedRun(
  nodes: Pick<GraphNode, "type" | "config">[],
  workflows: { id: string; has_external: boolean; has_pause?: boolean }[],
): boolean {
  return nodes.some(
    (node) =>
      ["agent", "llm", "mcp_tool", "http_tool", "approval", "wait"].includes(
        node.type,
      ) ||
      (["subworkflow", "for_each"].includes(node.type) &&
        (workflows.find((option) => option.id === node.config.version_id)
          ?.has_external !== false ||
          workflows.find((option) => option.id === node.config.version_id)
            ?.has_pause === true)),
  );
}

export type Reference =
  { kind: "literal"; value: unknown } | { kind: "input"; pointer: string };
export type NodeIssue = ValidationIssue & { severity: "error" | "warning" };
export type NodeIssues = Record<string, NodeIssue[]>;

export const OPERATORS = [
  { value: "eq", label: "equals" },
  { value: "ne", label: "does not equal" },
  { value: "gt", label: "is greater than" },
  { value: "gte", label: "is at least" },
  { value: "lt", label: "is less than" },
  { value: "lte", label: "is at most" },
  { value: "contains", label: "contains" },
  { value: "exists", label: "exists" },
] as const;

export function operatorLabel(operator: unknown): string {
  return (
    OPERATORS.find((item) => item.value === operator)?.label ??
    String(operator ?? "?")
  );
}

/** Group a backend check by node so the canvas and inspector read the same result. */
export function issuesByNode(check: Validation | null): NodeIssues {
  const grouped: NodeIssues = {};
  for (const [list, severity] of [
    [check?.errors ?? [], "error"],
    [check?.warnings ?? [], "warning"],
  ] as const) {
    for (const issue of list) {
      if (!issue.node_id) continue;
      (grouped[issue.node_id] ??= []).push({ ...issue, severity });
    }
  }
  return grouped;
}

/** Issues at `path`, or below it unless `exact` (config.left also matches config.left.pointer). */
export function issuesAt(
  issues: NodeIssue[],
  path: string,
  exact = false,
): NodeIssue[] {
  const seen = new Set<string>();
  return issues.filter((issue) => {
    const hit =
      issue.path === path || (!exact && !!issue.path?.startsWith(`${path}.`));
    if (!hit || seen.has(issue.message)) return false;
    seen.add(issue.message);
    return true;
  });
}

export function upstreamIds(
  edges: { source: string; target: string }[],
  nodeId: string,
): string[] {
  const found = new Set<string>();
  const pending = edges
    .filter((edge) => edge.target === nodeId)
    .map((edge) => edge.source);
  while (pending.length) {
    const id = pending.pop()!;
    if (found.has(id)) continue;
    found.add(id);
    pending.push(
      ...edges.filter((edge) => edge.target === id).map((edge) => edge.source),
    );
  }
  return [...found];
}

/** Field paths suggested from the workflow input schema, two levels deep. */
export function inputFieldHints(
  schema: unknown,
  prefix = "",
  depth = 0,
): string[] {
  const properties = (schema as { properties?: Record<string, unknown> } | null)
    ?.properties;
  if (!properties || typeof properties !== "object" || depth > 1) return [];
  return Object.entries(properties).flatMap(([key, child]) => {
    const path = `${prefix}/${key.replaceAll("~", "~0").replaceAll("/", "~1")}`;
    return [path, ...inputFieldHints(child, path, depth + 1)];
  });
}

export function templatePlaceholders(template: unknown): string[] {
  return typeof template === "string"
    ? [...template.matchAll(/\{\{(.*?)\}\}/g)].map((match) => match[1])
    : [];
}

export function isReference(value: unknown): value is Reference {
  const kind = (value as { kind?: unknown } | null)?.kind;
  return kind === "literal" || kind === "input";
}

export function describeReference(value: unknown): string {
  if (!isReference(value)) return "?";
  if (value.kind === "input") return value.pointer || "input";
  return JSON.stringify(value.value) ?? "?";
}

/** Steps whose saved outputs a result reads, for the "earlier step outputs" test sample. */
export function resultSources(node: GraphNode): string[] {
  if (node.type !== "result") return [];
  const references = node.config.fields
    ? Object.values(
        node.config.fields as Record<
          string,
          { kind?: string; node_id?: string }
        >,
      )
    : [node.config.value as { kind?: string; node_id?: string } | undefined];
  return [
    ...new Set(
      references.flatMap((item) =>
        item?.kind === "output" && item.node_id ? [item.node_id] : [],
      ),
    ),
  ];
}

/** Mappings other than the identity {"from": "", "to": ""} reshape data between steps. */
export function reshapes(
  mappings: { from: string; to: string }[] | undefined,
): boolean {
  return !!mappings?.some(
    (mapping) => mapping.from !== "" || mapping.to !== "",
  );
}

/** One-line summary for a configured canvas node; null falls back to the kind's description. */
export function configSummary(
  node: GraphNode,
  toolNames: Record<string, string> = {},
): string | null {
  const config = node.config;
  switch (node.type) {
    case "approval":
      return typeof config.prompt === "string"
        ? config.prompt
        : "Owner or admin decision required";
    case "wait":
      return `Resume after ${config.seconds ?? "?"} seconds`;
    case "merge":
      return config.mode === "all"
        ? "Merge every connected path"
        : "Merge active paths";
    case "condition":
      if (!config.operator) return null;
      return config.operator === "exists"
        ? `${describeReference(config.left)} exists`
        : `${describeReference(config.left)} ${operatorLabel(config.operator)} ${describeReference(config.right)}`;
    case "transform": {
      const names = Object.keys(
        (config.fields as Record<string, unknown>) ?? {},
      );
      return names.length
        ? `Builds ${names.slice(0, 3).join(", ")}${names.length > 3 ? ` +${names.length - 3}` : ""}`
        : null;
    }
    case "text_template":
      return typeof config.template === "string" && config.template
        ? config.template
        : null;
    case "list_filter":
      return config.source !== undefined
        ? `Keep ${config.source || "input"} items where ${config.item_pointer || "item"} ${operatorLabel(config.operator)}${config.operator === "exists" ? "" : ` ${JSON.stringify(config.value)}`}`
        : null;
    case "json_parse":
      return config.source !== undefined
        ? `Parse ${config.source || "input"}`
        : null;
    case "tool":
      return typeof config.tool_key === "string"
        ? (toolNames[config.tool_key] ?? config.tool_key)
        : null;
    case "llm": {
      if (!config.model_id) return null;
      const tools = ["tool_keys", "mcp_tools", "http_tools"].reduce((sum, key) => sum + ((config[key] as unknown[]) ?? []).length, 0);
      return `${config.model_id}${tools ? ` · ${tools} tool${tools === 1 ? "" : "s"}` : ""}`;
    }
    case "mcp_tool":
      return config.tool_name
        ? `${config.server_id} · ${config.tool_name}`
        : null;
    case "http_tool":
      return config.tool_id ? "Approved HTTP API endpoint" : null;
    case "subworkflow":
      return config.version_id
        ? `Calls ${toolNames[String(config.version_id)] ?? "a published workflow"}`
        : null;
    case "for_each":
      return config.source
        ? `Each ${config.source} item → ${toolNames[String(config.version_id)] ?? "choose a workflow"} · max ${config.max_items ?? "?"}`
        : null;
    case "result": {
      const fields = Object.keys(
        (config.fields as Record<string, unknown>) ?? {},
      );
      if (fields.length)
        return `Returns { ${fields.slice(0, 3).join(", ")}${fields.length > 3 ? ", …" : ""} }`;
      const value = config.value as
        { node_id?: string; pointer?: string } | undefined;
      return value?.node_id
        ? `Returns ${value.node_id}${value.pointer || ""}`
        : "Returns the incoming data";
    }
    default:
      return null;
  }
}

/** Text of a run's output: a `reply` field when present, otherwise the JSON itself. */
export function replyText(output: unknown): string {
  if (typeof output === "string") return output;
  const reply = (output as { reply?: unknown } | null)?.reply;
  return typeof reply === "string" ? reply : JSON.stringify(output, null, 2);
}
