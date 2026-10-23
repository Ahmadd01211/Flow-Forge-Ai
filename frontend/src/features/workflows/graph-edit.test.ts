import { describe, expect, it } from "vitest";
import { connectInsertedNode } from "./graph-edit";

describe("workflow step insertion", () => {
  it("keeps input mappings and connects a new step before the result", () => {
    const before = [{ id: "input-result", source: "input", target: "result", sourceHandle: "out", targetHandle: "in", data: { mappings: [{ from: "", to: "" }] } }];
    const after = connectInsertedNode(before, "input", "tool-1", before[0], "tool-result");
    expect(after.map((edge) => [edge.source, edge.target])).toEqual([["input", "tool-1"], ["tool-1", "result"]]);
    expect(after[0].data?.mappings).toEqual([{ from: "", to: "" }]);
    expect(after[1].data?.mappings).toEqual([]);
    expect(before[0].target).toBe("result");
  });
});
