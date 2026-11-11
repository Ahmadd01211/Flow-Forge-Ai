/** Shapes from GET /runs/{id}/trace and /agents/{id}/performance, plus pure display helpers. */

export interface TraceStep {
  kind: "model" | "tool" | "skill";
  label: string;
  status: string;
  error_code: string | null;
  started_at: string | null;
  finished_at: string;
  duration_ms: number | null;
  input_tokens: number | null;
  output_tokens: number | null;
  cost_usd: string | null;
  arguments: unknown;
  output: unknown;
}
export interface Feedback {
  up: number;
  down: number;
  mine: { rating: "up" | "down"; comment: string } | null;
  comments: { rating: "up" | "down"; comment: string; author: string; created_at: string }[];
}
export interface TraceData {
  run: { id: string; state: string; output: unknown; error_code: string | null; cost_usd: string | null; uncertain_cost_usd: string | null; input_tokens: number | null; output_tokens: number | null; created_at: string; started_at: string | null; finished_at: string | null };
  input: unknown;
  agent: { id: string; workflow_id: string | null; name: string; version_number: number; provider: string; model_id: string; playground: boolean; skills: { name: string; number: number | null }[]; source: string };
  steps: TraceStep[];
  totals: { duration_ms: number | null; model_calls: number; tool_calls: number };
  feedback: Feedback;
}
export interface Performance {
  days: number;
  include_tests: boolean;
  runs: number;
  completed: number;
  failed: number;
  success_rate: number | null;
  cost_total_usd: string;
  cost_avg_usd: string | null;
  duration_p50_s: number | null;
  duration_p95_s: number | null;
  tokens_avg: number | null;
  daily: { date: string; runs: number; failed: number; cost_usd: string }[];
  tools: { tool_key: string; label: string; kind: "tool" | "skill"; calls: number; failed: number }[];
  errors: { code: string; count: number }[];
  feedback: { up: number; down: number; recent_down: { run_id: string; comment: string; created_at: string }[] };
  recent: { id: string; state: string; created_at: string; source: string; error_code: string | null; cost_usd: string | null; duration_s: number | null }[];
}

/** Each step's bar as a share of the run: where it starts and how wide it is, in percent. */
export function waterfall(steps: TraceStep[], runStart: string | null, runEnd: string | null): { left: number; width: number }[] {
  const times = steps.flatMap((step) => [step.started_at, step.finished_at]).filter(Boolean).map((value) => Date.parse(value as string));
  const start = runStart ? Date.parse(runStart) : Math.min(...times);
  const end = runEnd ? Date.parse(runEnd) : Math.max(...times);
  const span = Math.max(end - start, 1);
  return steps.map((step) => {
    const from = step.started_at ? Date.parse(step.started_at) : Date.parse(step.finished_at);
    const to = Date.parse(step.finished_at);
    const left = Math.min(Math.max(((from - start) / span) * 100, 0), 100);
    return { left, width: Math.max(Math.min(((to - from) / span) * 100, 100 - left), 1.5) };
  });
}

export function ms(value: number | null): string {
  if (value === null) return "—";
  if (value < 1000) return `${value} ms`;
  return `${(value / 1000).toFixed(value < 10_000 ? 1 : 0)} s`;
}

export function usd(value: string | null | undefined, digits = 4): string {
  return value === null || value === undefined ? "—" : `$${Number(value).toFixed(digits)}`;
}

export const STEP_ICON: Record<TraceStep["kind"], string> = { model: "🧠", tool: "🔧", skill: "📘" };
