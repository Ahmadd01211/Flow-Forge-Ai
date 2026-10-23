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
export type NodeKind =
  "manual_input" | "webhook_trigger" | "schedule_trigger" | "agent" | "tool" | "mcp_tool" | "condition" | "transform" | "text_template" | "list_filter" | "json_parse" | "result";
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
export interface Validation {
  valid: boolean;
  publishable: boolean;
  revision: number;
  scope: string;
  errors: {
    code: string;
    message: string;
    node_id?: string;
    edge_id?: string;
    path?: string;
  }[];
  warnings: unknown[];
}
export interface List<T> {
  items: T[];
  next_cursor: string | null;
}
