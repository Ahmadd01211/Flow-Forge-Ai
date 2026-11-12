import { describe, expect, it, vi } from "vitest";
import { loadRecipeSample } from "./recipe-handoff";

describe("recipe metadata handoff", () => {
  it("loads only source sample and expected example, never graph or settings", async () => {
    const fetch = vi
      .fn()
      .mockResolvedValue({
        key: "remove-duplicates",
        kind: "workflow",
        sample_input: { items: [1, 1] },
        expected_result: "One item",
        graph: { nodes: [] },
      });
    expect(
      await loadRecipeSample("remove-duplicates", "workflow", fetch),
    ).toEqual({ sampleInput: { items: [1, 1] }, expectedResult: "One item" });
    expect(fetch).toHaveBeenCalledWith("/templates/remove-duplicates");
  });
  it.each([
    undefined,
    ["a", "b"],
    "../secrets",
    "x?query=yes",
    "",
    "x".repeat(129),
  ])("ignores absent or invalid query %s", async (key) => {
    const fetch = vi.fn();
    expect(await loadRecipeSample(key, "workflow", fetch)).toBeUndefined();
    expect(fetch).not.toHaveBeenCalled();
  });
  it.each([
    null,
    [],
    {},
    { kind: "agent", sample_input: {} },
    { kind: "workflow", sample_input: [] },
    { kind: "workflow", sample_input: "bad" },
    { kind: "workflow", expected_result: 123 },
  ])("ignores malformed or unrelated recipe %j", async (value) => {
    expect(
      await loadRecipeSample(
        "local",
        "workflow",
        vi.fn().mockResolvedValue(value),
      ),
    ).toBeUndefined();
  });
  it("keeps a sample-free custom recipe empty and survives a failed fetch", async () => {
    expect(
      await loadRecipeSample(
        "custom",
        "agent",
        vi.fn().mockResolvedValue({ kind: "agent" }),
      ),
    ).toEqual({});
    expect(
      await loadRecipeSample(
        "local",
        "workflow",
        vi.fn().mockRejectedValue(new Error("unavailable")),
      ),
    ).toBeUndefined();
  });
});
