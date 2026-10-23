import { describe, expect, it } from "vitest";
import { compareDefinitions } from "./version-diff";
import type { AgentConfig } from "@/lib/api/types";
const config: AgentConfig = {
  schema_version: 1,
  instructions: "Classify",
  provider: "openai",
  model_id: "",
  tool_keys: [],
  input_schema: { type: "object", properties: { ticket: { type: "string" } } },
  output_schema: { type: "object" },
  limits: {
    max_iterations: 8,
    timeout_seconds: 60,
    max_cost_usd: "0.1",
    max_tool_calls: 8,
    max_output_tokens: 4096,
  },
};
const before = { name: "Triage", description: "", config };
describe("snapshot differences", () => {
  it("detects changed instructions and nested budget without changing its inputs", () => {
    const original = structuredClone(before);
    const after = structuredClone(before);
    after.config.instructions = "New instructions";
    after.config.limits.timeout_seconds = 30;
    expect(compareDefinitions(before, after).map((c) => c.path)).toEqual([
      "/config/instructions",
      "/config/limits/timeout_seconds",
    ]);
    expect(before).toEqual(original);
  });
  it("ignores schema object key ordering", () => {
    const after = structuredClone(before);
    after.config.input_schema = {
      properties: { ticket: { type: "string" } },
      type: "object",
    };
    expect(compareDefinitions(before, after)).toEqual([]);
  });
  it("reports removals and escaped property names", () => {
    const after = structuredClone(before);
    after.config.input_schema = {
      type: "object",
      properties: { "ticket/text": { type: "string" } },
    };
    expect(compareDefinitions(before, after).map((c) => c.path)).toEqual([
      "/config/input_schema/properties/ticket",
      "/config/input_schema/properties/ticket~1text",
    ]);
  });
});
