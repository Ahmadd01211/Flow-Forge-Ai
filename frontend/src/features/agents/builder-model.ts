/** Pure helpers for the agent builder: presets, tone snippets, readiness and cost estimates. */
import type { AgentConfig, Connection } from "@/lib/api/types";

type Schema = AgentConfig["input_schema"];

export const CHAT_INPUT: Schema = {
  type: "object",
  properties: {
    conversation_id: { type: "string", description: "Keeps one conversation together for memory." },
    message: { type: "string", description: "What the person said." },
  },
  required: ["message"],
  additionalProperties: false,
};
export const REPLY_OUTPUT: Schema = {
  type: "object",
  properties: { reply: { type: "string", description: "The agent's answer." } },
  required: ["reply"],
  additionalProperties: false,
};

export const IO_PRESETS = [
  { id: "chat", emoji: "💬", label: "Chat", description: "A message in, a reply out. Works with memory and the chat page.", input: CHAT_INPUT, output: REPLY_OUTPUT },
  {
    id: "classify", emoji: "🏷️", label: "Classify", description: "Sort text into labels you choose.",
    input: { type: "object", properties: { text: { type: "string" } }, required: ["text"], additionalProperties: false },
    output: { type: "object", properties: { label: { type: "string", enum: ["urgent", "normal"] }, reason: { type: "string" } }, required: ["label", "reason"], additionalProperties: false },
  },
  {
    id: "extract", emoji: "📇", label: "Extract", description: "Pull structured fields out of messy text.",
    input: { type: "object", properties: { text: { type: "string" } }, required: ["text"], additionalProperties: false },
    output: { type: "object", properties: { name: { type: "string" }, email: { type: "string" }, request: { type: "string" } }, required: ["name", "email", "request"], additionalProperties: false },
  },
] as const;

/**
 * Presets match on structure alone: descriptions are documentation, and stored schemas come back
 * with their keys reordered by Postgres, so keys are sorted before comparing.
 */
function shape(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(shape);
  if (!value || typeof value !== "object") return value;
  return Object.fromEntries(
    Object.entries(value).filter(([key]) => key !== "description").sort(([left], [right]) => left.localeCompare(right)).map(([key, child]) => [key, shape(child)]),
  );
}

export function presetOf(input: string, output: string): string {
  const same = (text: string, schema: unknown) => {
    try {
      return JSON.stringify(shape(JSON.parse(text))) === JSON.stringify(shape(schema));
    } catch {
      return false;
    }
  };
  return IO_PRESETS.find((preset) => same(input, preset.input) && same(output, preset.output))?.id ?? "custom";
}

export const TONES = [
  { id: "concise", label: "Concise", snippet: "Keep answers short and to the point." },
  { id: "friendly", label: "Friendly", snippet: "Be warm and friendly, and use plain language." },
  { id: "formal", label: "Formal", snippet: "Use a professional, formal tone." },
  { id: "steps", label: "Step by step", snippet: "Explain your answer in clear, numbered steps." },
  { id: "careful", label: "Careful", snippet: "If you are not sure, say so and ask a clarifying question instead of guessing." },
] as const;

export const SNIPPETS = [
  { label: "Use tools first", text: "Use your tools to look things up instead of answering from memory." },
  { label: "No made-up facts", text: "Never invent order numbers, prices, names or other facts you were not given." },
  { label: "Stay on topic", text: "Politely decline requests that are outside your job." },
  { label: "Cite sources", text: "Say which tool or document each fact came from." },
] as const;

/** Add a snippet as its own line, or remove it when already present. */
export function toggleLine(instructions: string, line: string): string {
  const lines = instructions.split("\n");
  if (lines.some((item) => item.trim() === line)) return lines.filter((item) => item.trim() !== line).join("\n").replace(/\n{3,}/g, "\n\n").trim();
  return `${instructions.trimEnd()}${instructions.trim() ? "\n" : ""}${line}`;
}

export function hasLine(instructions: string, line: string): boolean {
  return instructions.split("\n").some((item) => item.trim() === line);
}

export function isChatInput(schema: unknown): boolean {
  const message = (schema as { properties?: Record<string, { type?: string }> } | null)?.properties?.message;
  return message?.type === "string";
}

export function toolCount(config: Pick<AgentConfig, "tool_keys" | "mcp_tools" | "http_tools">): number {
  return config.tool_keys.length + config.mcp_tools.length + config.http_tools.length;
}

/** Strip the loop's family prefix from a run event's tool key: "mcp:docs__search" → "docs__search". */
export function toolLabel(key: string | null): string {
  if (key?.startsWith("skill:")) return `skill · ${key.slice(6)}`;
  return (key ?? "tool").replace(/^(mcp|http|workflow):/, "").replaceAll("__", " · ");
}

/**
 * Rough runs per dollar for one model call of ~2,000 input and ~400 output tokens, doubled when
 * tools are on (one call to decide, one to answer). Null when the provider publishes no prices.
 */
export function runsPerDollar(capability: { input_usd_per_million?: string | null; output_usd_per_million?: string | null } | undefined, tools: boolean): number | null {
  const input = Number(capability?.input_usd_per_million ?? NaN), output = Number(capability?.output_usd_per_million ?? NaN);
  if (!Number.isFinite(input) || !Number.isFinite(output) || input + output <= 0) return null;
  const cost = ((2000 * input + 400 * output) / 1_000_000) * (tools ? 2 : 1);
  return Math.floor(1 / cost);
}

export type BlockId = "persona" | "brain" | "tools" | "memory" | "io" | "guardrails";

/** Which required blocks are complete, from what the editor can check without a server call. */
export function blockReadiness(
  config: AgentConfig,
  connection: Connection | undefined,
  schemasValid: boolean,
): Record<BlockId, boolean> {
  return {
    persona: config.instructions.trim().length > 0,
    brain: connection?.state === "active" && connection.verified_models.includes(config.model_id),
    tools: !toolCount(config) || config.limits.max_tool_calls > 0,
    memory: !config.memory || config.memory.key_pointer.length > 1,
    io: schemasValid,
    guardrails: Number(config.limits.max_cost_usd) > 0,
  };
}

/** Readiness issue sections from the server checklist map onto builder blocks. */
export const SECTION_BLOCK: Record<string, BlockId | "skills"> = { instructions: "persona", model: "brain", schemas: "io", limits: "guardrails", skills: "skills" };
