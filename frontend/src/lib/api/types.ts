export interface Workspace {
  id: string;
  name: string;
  role: "owner" | "admin" | "editor" | "viewer";
}
export interface SessionData {
  user: { id: string; name: string; email: string; email_verified: boolean };
  workspaces: Workspace[];
  csrf_token: string;
}
import type { components } from "./generated";
export type AgentConfig = components["schemas"]["AgentConfig-Output"];
export type Agent = components["schemas"]["AgentRead"];
export type AgentVersion = components["schemas"]["VersionRead"];
export type VersionList = components["schemas"]["VersionList"];
export type ExampleResult = components["schemas"]["ExampleResult"];
export type Connection = components["schemas"]["ConnectionRead"];
export type ConnectionList = components["schemas"]["ConnectionList"];
export type AgentRun = components["schemas"]["RunRead"];
export type RunEvent = components["schemas"]["RunEventRead"];
export type RunList = components["schemas"]["RunList"];
export type NodeKind = components["schemas"]["Node"]["type"];
export interface GraphNode {
  id: string;
  type: NodeKind;
  label: string;
  position: { x: number; y: number };
  join: "all" | "active";
  config: Record<string, unknown>;
  policy: Record<string, unknown>;
}
export interface GraphEdge {
  id: string;
  source: string;
  source_port: "out" | "true" | "false";
  target: string;
  target_port: "in";
  mappings: { from: string; to: string }[];
}
export interface Graph {
  schema_version: 1;
  nodes: GraphNode[];
  edges: GraphEdge[];
  input_schema: Record<string, unknown>;
  output_schema: Record<string, unknown>;
  limits: Record<string, unknown>;
}
export interface Workflow {
  id: string;
  workspace_id: string;
  name: string;
  description: string;
  graph: Graph;
  revision: number;
  updated_at: string;
}
export interface ValidationIssue {
  code: string;
  message: string;
  node_id?: string | null;
  edge_id?: string | null;
  path?: string | null;
}
export interface Validation {
  valid: boolean;
  publishable: boolean;
  /** Present for saved-revision validation; absent for a live draft check. */
  revision?: number;
  scope: string;
  errors: ValidationIssue[];
  warnings: ValidationIssue[];
  expanded_steps?: number;
  agent_steps?: number;
  has_external?: boolean;
}
export interface AgentRunSummary {
  id: string;
  state: "queued" | "running" | "completed" | "failed" | "cancelled";
  output: Record<string, unknown> | null;
  error_code: string | null;
  reserved_max_usd: string;
  cost_usd: string | null;
  uncertain_cost_usd: string | null;
  input_tokens: number | null;
  output_tokens: number | null;
}
export interface NodeTestResult {
  node_id: string;
  type: NodeKind;
  status: "completed" | "failed" | "queued";
  output: unknown;
  selected_port: "true" | "false" | null;
  error: { code: string; message: string } | null;
  duration_ms: number;
  external: boolean;
  agent_run: AgentRunSummary | null;
}
export interface ToolOption {
  key: string;
  name: string;
  description: string;
  input_schema: { properties?: Record<string, unknown>; required?: string[] };
  installed: boolean;
}
export interface List<T> {
  items: T[];
  next_cursor: string | null;
}
