/** Shapes and pure helpers for the workspace Overview; mirrors GET /workspaces/{id}/overview. */

export type RunSource = "manual" | "chat" | "webhook" | "schedule" | "deployment" | "replay" | "test";
export type RunState = "queued" | "running" | "waiting" | "completed" | "failed" | "cancelled";

export interface OverviewData {
  role: "owner" | "admin" | "editor" | "viewer";
  can_decide: boolean;
  counts: { agents: number; workflows: number };
  setup: { provider_connected: boolean; published: boolean; succeeded: boolean; trigger: boolean; teammates: boolean; complete: boolean };
  usage: {
    accepted_runs: number;
    daily_run_limit: number;
    active_runs: number;
    active_run_limit: number;
    daily_budget_usd: string;
    measured_usd: string;
    uncertain_usd: string;
    reserved_usd: string;
    committed_usd: string;
    input_tokens: number;
    output_tokens: number;
    completed_today: number;
    failed_today: number;
    resets_at: string;
  };
  trend: { date: string; runs: number; failed: number; cost_usd: string }[];
  attention: {
    approvals: {
      pause_id: string;
      run_id: string;
      node_id: string;
      workflow_name: string;
      version_number: number;
      step_label: string;
      prompt: string;
      created_at: string;
      due_at: string;
      requested_by_you: boolean;
      allow_requester: boolean;
    }[];
    approvals_total: number;
    failed_runs_24h: number;
    stale_agents: { agent_id: string; name: string; version_number: number; reason: "provider_disconnected" | "credential_changed" }[];
    trigger_errors: { id: string; name: string; kind: string; last_error_code: string }[];
    near_limits: { spend: boolean; runs: boolean; spend_ratio: number; run_ratio: number };
  };
  recent_runs: {
    kind: "workflow" | "agent";
    id: string;
    name: string;
    version_number: number;
    owner_id: string;
    state: RunState;
    source: RunSource;
    error_code: string | null;
    created_at: string;
    finished_at: string | null;
    duration_seconds: number | null;
    cost_usd: string | null;
  }[];
  recent_edits: { kind: "workflow" | "agent"; id: string; name: string; updated_at: string; status: "draft" | "published" | "changed"; version_number: number | null }[];
  triggers: {
    schedules: { id: string; name: string; next_due_at: string | null; cron_expression: string | null; interval_seconds: number | null; timezone: string | null; last_error_code: string | null }[];
    webhooks: { id: string; name: string; last_error_code: string | null }[];
    chat: { workflow_id: string; name: string; version_number: number }[];
    deployments: number;
  };
  activity: { id: string; action: string; actor_name: string; target_id: string; details: Record<string, unknown>; created_at: string }[] | null;
}

export type AttentionItem = { key: string; tone: "warning" | "critical"; text: string; href: string; action: string };

export const SOURCE_LABELS: Record<RunSource, string> = {
  manual: "Manual",
  chat: "Chat",
  webhook: "Webhook",
  schedule: "Schedule",
  deployment: "API",
  replay: "Replay",
  test: "Step test",
};

const ACTIVITY: Record<string, string> = {
  "agent.published": "published an agent",
  "agent.snapshot_created": "saved an agent snapshot",
  "agent.version_restored": "restored an agent version",
  "agent.evaluation_created": "ran an agent evaluation",
  "agent_run.submitted": "started an agent run",
  "agent_run.cancel_requested": "cancelled an agent run",
  "workflow.published": "published a workflow",
  "workflow.node_tested": "tested a workflow step",
  "workflow_run.submitted": "started a workflow run",
  "workflow_run.cancel_requested": "cancelled a workflow run",
  "workflow_run.replayed": "replayed a workflow run",
  "workflow_pause.created": "requested an approval",
  "workflow_pause.approved": "approved a paused run",
  "workflow_pause.rejected": "rejected a paused run",
  "workflow_pause.elapsed": "resumed a run after its timer",
  "workflow_pause.expired": "let an approval expire",
  "workflow_pause.cancelled": "cancelled a paused run",
  "automation.created": "created a trigger",
  "automation.state_changed": "paused or resumed a trigger",
  "automation.key_rotated": "rotated a webhook key",
  "automation.archived": "archived a trigger",
  "deployment.created": "created a deployment",
  "deployment.rotated": "rotated a deployment key",
  "deployment.revoked": "revoked a deployment",
  "provider.connected": "connected a model provider",
  "provider.rotated": "replaced a provider key",
  "provider.revoked": "disconnected a model provider",
  "provider.default_model_changed": "changed the default model",
  "provider.models_refreshed": "refreshed provider models",
  "mcp.server_added": "added an MCP server",
  "mcp.connected": "connected an MCP server",
  "mcp.revoked": "disconnected an MCP server",
  "mcp.tool_policy_changed": "changed MCP tool permissions",
  "http_tool.approved": "approved an HTTP tool",
  "http_tool.credential_rotated": "replaced an HTTP tool credential",
  "http_tool.revoked": "revoked an HTTP tool",
  "http_tool.tested": "tested an HTTP tool",
  "tool.installed": "approved a built-in tool",
  "tool.removed": "removed a built-in tool",
  "template.created": "saved a template",
  "template.imported": "imported a template",
  "template.instantiated": "created from a template",
  "template.sharing_changed": "changed template sharing",
  "workspace.invited": "invited a teammate",
  "workspace.invitation_accepted": "joined the workspace",
  "workspace.invitation_revoked": "revoked an invitation",
  "workspace.member_removed": "removed a member",
  "workspace.member_role_changed": "changed a member's role",
  "workspace.renamed": "renamed the workspace",
  "workspace.limits_changed": "changed workspace limits",
};

/** "approved an HTTP tool"; unknown actions fall back to readable words. */
export function activityLabel(action: string): string {
  return ACTIVITY[action] ?? action.replace(/[._]/g, " ");
}

export function setupSteps(setup: OverviewData["setup"], base: string) {
  return [
    { key: "provider", done: setup.provider_connected, title: "Connect a model provider", description: "Add an API key so agents and LLM steps can call a model.", href: `${base}/integrations`, action: "Open integrations" },
    { key: "publish", done: setup.published, title: "Publish a workflow or agent", description: "Publishing freezes a version that runs, deploys and can be triggered.", href: `${base}/workflows`, action: "Open workflows" },
    { key: "run", done: setup.succeeded, title: "Complete a successful run", description: "Run a published version and inspect its steps, output and cost.", href: `${base}/executions`, action: "Open executions" },
    { key: "trigger", done: setup.trigger, title: "Add a way to start it", description: "A schedule, webhook, chat trigger or deployment API key.", href: `${base}/automations`, action: "Set up a trigger" },
    { key: "team", done: setup.teammates, optional: true, title: "Invite a teammate", description: "Optional: share the workspace with an editor or reviewer.", href: `${base}/settings`, action: "Invite" },
  ];
}

export function attentionItems(data: OverviewData, base: string): AttentionItem[] {
  const { attention } = data;
  const items: AttentionItem[] = [];
  if (attention.failed_runs_24h)
    items.push({ key: "failed", tone: "critical", text: `${attention.failed_runs_24h} failed run${attention.failed_runs_24h === 1 ? "" : "s"} in the last 24 hours`, href: `${base}/executions?kind=workflows`, action: "Review runs" });
  for (const agent of attention.stale_agents)
    items.push({
      key: `agent-${agent.agent_id}`,
      tone: "critical",
      text: agent.reason === "provider_disconnected"
        ? `${agent.name} v${agent.version_number} can't run: its model provider is disconnected`
        : `${agent.name} v${agent.version_number} uses a replaced provider key and needs republishing`,
      href: agent.reason === "provider_disconnected" ? `${base}/integrations` : `${base}/agents/${agent.agent_id}`,
      action: agent.reason === "provider_disconnected" ? "Reconnect" : "Republish",
    });
  for (const trigger of attention.trigger_errors)
    items.push({ key: `trigger-${trigger.id}`, tone: "warning", text: `${trigger.name} (${trigger.kind}) last failed with ${trigger.last_error_code}`, href: `${base}/automations`, action: "Check trigger" });
  if (attention.near_limits.spend)
    items.push({ key: "spend", tone: "warning", text: `${percent(attention.near_limits.spend_ratio)} of today's budget is committed`, href: `${base}/usage`, action: "View usage" });
  if (attention.near_limits.runs)
    items.push({ key: "runs", tone: "warning", text: `${percent(attention.near_limits.run_ratio)} of today's run limit is used`, href: `${base}/usage`, action: "View usage" });
  return items;
}

export function percent(ratio: number): string {
  return `${Math.round(ratio * 100)}%`;
}

export function money(value: string | number): string {
  const amount = Number(value);
  return `$${amount < 1 && amount > 0 ? amount.toFixed(4) : amount.toFixed(2)}`;
}

export function duration(seconds: number | null): string {
  if (seconds === null) return "—";
  if (seconds < 60) return `${seconds < 10 ? seconds.toFixed(1) : Math.round(seconds)}s`;
  return `${Math.floor(seconds / 60)}m ${Math.round(seconds % 60)}s`;
}

/** Where a run's detail lives: workflow runs on the workflow tab, LLM step tests on their workflow. */
export function runHref(run: OverviewData["recent_runs"][number], base: string): string {
  if (run.kind === "workflow") return `${base}/executions?kind=workflows&runId=${run.id}`;
  return `${base}/executions?runId=${run.id}`;
}

export function editHref(edit: OverviewData["recent_edits"][number], base: string): string {
  return edit.kind === "workflow" ? `${base}/workflows/${edit.id}/edit` : `${base}/agents/${edit.id}`;
}

/** Bar heights as percentages of the tallest day; an all-zero week stays flat. */
export function barHeights(values: number[]): number[] {
  const top = Math.max(...values, 0);
  return values.map((value) => (top > 0 ? Math.max(value > 0 ? 4 : 0, (value / top) * 100) : 0));
}
