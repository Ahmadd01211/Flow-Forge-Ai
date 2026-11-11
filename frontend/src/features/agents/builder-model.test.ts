import { describe, expect, it } from "vitest";
import { CHAT_INPUT, IO_PRESETS, REPLY_OUTPUT, blockReadiness, hasLine, isChatInput, presetOf, runsPerDollar, toggleLine, toolLabel } from "./builder-model";
import { matches, needsAttention, type LibraryAgent } from "./library-model";

describe("agent builder helpers", () => {
  it("toggles instruction snippets as whole lines", () => {
    const once = toggleLine("You help customers.", "Keep answers short.");
    expect(once).toBe("You help customers.\nKeep answers short.");
    expect(hasLine(once, "Keep answers short.")).toBe(true);
    expect(toggleLine(once, "Keep answers short.")).toBe("You help customers.");
    expect(toggleLine("", "Be careful.")).toBe("Be careful.");
  });

  it("recognises presets and chat-shaped input", () => {
    expect(presetOf(JSON.stringify(CHAT_INPUT, null, 2), JSON.stringify(REPLY_OUTPUT))).toBe("chat");
    expect(presetOf(JSON.stringify(IO_PRESETS[1].input), JSON.stringify(IO_PRESETS[1].output))).toBe("classify");
    // As stored: no descriptions, keys in Postgres order.
    const bare = { required: ["message"], type: "object", additionalProperties: false, properties: { message: { type: "string" }, conversation_id: { type: "string" } } };
    expect(presetOf(JSON.stringify(bare), JSON.stringify(REPLY_OUTPUT))).toBe("chat");
    expect(presetOf("{}", "{}")).toBe("custom");
    expect(presetOf("not json", "{}")).toBe("custom");
    expect(isChatInput(CHAT_INPUT)).toBe(true);
    expect(isChatInput({ type: "object", properties: { text: { type: "string" } } })).toBe(false);
  });

  it("estimates runs per dollar and labels tool events", () => {
    expect(runsPerDollar({ input_usd_per_million: "0.25", output_usd_per_million: "2" }, false)).toBe(expectedRuns(0.25, 2, 1));
    expect(runsPerDollar({ input_usd_per_million: "0.25", output_usd_per_million: "2" }, true)).toBe(expectedRuns(0.25, 2, 2));
    expect(runsPerDollar({ input_usd_per_million: null, output_usd_per_million: null }, false)).toBeNull();
    expect(toolLabel("mcp:github__search_issues")).toBe("github · search_issues");
    expect(toolLabel("text.replace")).toBe("text.replace");
  });

  it("marks blocks ready from the draft alone", () => {
    const config = {
      instructions: "Help.", provider: "openai", model_id: "gpt-5-mini", tool_keys: [], mcp_tools: [], http_tools: [],
      memory: null, limits: { max_cost_usd: "0.10", max_tool_calls: 8 },
    } as unknown as Parameters<typeof blockReadiness>[0];
    const connection = { state: "active", verified_models: ["gpt-5-mini"] } as unknown as Parameters<typeof blockReadiness>[1];
    expect(Object.values(blockReadiness(config, connection, true)).every(Boolean)).toBe(true);
    const unfinished = blockReadiness({ ...config, instructions: " ", model_id: "other" }, connection, false);
    expect([unfinished.persona, unfinished.brain, unfinished.io]).toEqual([false, false, false]);
  });
});

function expectedRuns(input: number, output: number, calls: number) {
  return Math.floor(1 / (((2000 * input + 400 * output) / 1_000_000) * calls));
}

describe("agent library filters", () => {
  const agent = (overrides: Partial<LibraryAgent>): LibraryAgent => ({
    id: "a", name: "Concierge", description: "Answers orders", revision: 1, updated_at: "", provider: "openai", model_id: "gpt-5-mini",
    tools: { builtin: [], mcp_servers: ["github"], http: [], count: 1 }, memory: false, status: "published",
    published: { version_id: "v", number: 1, runnable: true, chat_ready: true }, last_run: null, week: { completed: 3, failed: 0 },
    ...overrides,
  });
  it("finds agents that need attention and matches search across tools", () => {
    expect(needsAttention(agent({}))).toBe(false);
    expect(needsAttention(agent({ status: "changed" }))).toBe(true);
    expect(needsAttention(agent({ published: { version_id: "v", number: 1, runnable: false, chat_ready: true } }))).toBe(true);
    expect(needsAttention(agent({ week: { completed: 0, failed: 1 } }))).toBe(true);
    expect(matches(agent({}), "all", "github")).toBe(true);
    expect(matches(agent({}), "draft", "")).toBe(false);
    expect(matches(agent({ status: "draft", published: null }), "draft", "conc")).toBe(true);
  });
});
