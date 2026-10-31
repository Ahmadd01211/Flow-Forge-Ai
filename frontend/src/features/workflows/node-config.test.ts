import { describe, expect, it } from "vitest";
import type { GraphNode } from "@/lib/api/types";
import {
  configSummary,
  inputFieldHints,
  issuesAt,
  issuesByNode,
  reshapes,
  resultSources,
  templatePlaceholders,
  upstreamIds,
  requiresPublishedRun,
} from "./node-config";

const node = (
  type: GraphNode["type"],
  config: Record<string, unknown>,
): GraphNode => ({
  id: "step",
  type,
  label: "Step",
  position: { x: 0, y: 0 },
  join: "all",
  config,
  policy: {},
});

describe("nested workflow safety", () => {
  it("allows local preview only when the selected published dependency is known to be local", () => {
    const loop = node("for_each", { version_id: "child" });
    expect(requiresPublishedRun([loop], [])).toBe(true);
    expect(
      requiresPublishedRun([loop], [{ id: "child", has_external: true }]),
    ).toBe(true);
    expect(
      requiresPublishedRun([loop], [{ id: "child", has_external: false }]),
    ).toBe(false);
    expect(
      requiresPublishedRun(
        [loop, node("agent", {})],
        [{ id: "child", has_external: false }],
      ),
    ).toBe(true);
  });
});

describe("node configuration helpers", () => {
  it("requires durable runs for decisions, timers and paused children", () => {
    expect(requiresPublishedRun([node("approval", {})], [])).toBe(true);
    expect(requiresPublishedRun([node("wait", {})], [])).toBe(true);
    expect(
      requiresPublishedRun(
        [node("subworkflow", { version_id: "paused-child" })],
        [{ id: "paused-child", has_external: false, has_pause: true }],
      ),
    ).toBe(true);
    expect(configSummary(node("wait", { seconds: 120 }))).toBe(
      "Resume after 120 seconds",
    );
  });
  it("groups errors and warnings by node and matches field paths", () => {
    const grouped = issuesByNode({
      valid: false,
      publishable: false,
      scope: "",
      errors: [
        {
          code: "NODE_CONFIG_INVALID",
          message: "Bad pointer",
          node_id: "a",
          path: "config.left.pointer",
        },
        {
          code: "ENTRY_REQUIRED",
          message: "Graph-wide",
          node_id: null,
          path: null,
        },
      ],
      warnings: [
        {
          code: "NODE_CONFIG_UNUSED",
          message: "Unused",
          node_id: "a",
          path: "config.secret",
        },
      ],
    });
    expect(Object.keys(grouped)).toEqual(["a"]);
    expect(grouped.a.map((issue) => issue.severity)).toEqual([
      "error",
      "warning",
    ]);
    expect(issuesAt(grouped.a, "config.left")).toHaveLength(1);
    expect(issuesAt(grouped.a, "config.left", true)).toHaveLength(0);
    expect(issuesAt(grouped.a, "config.l")).toHaveLength(0);
  });

  it("walks upstream through branches without looping", () => {
    const edges = [
      { source: "input", target: "if" },
      { source: "if", target: "a" },
      { source: "if", target: "b" },
      { source: "a", target: "result" },
      { source: "b", target: "result" },
    ];
    expect(upstreamIds(edges, "result").sort()).toEqual([
      "a",
      "b",
      "if",
      "input",
    ]);
    expect(upstreamIds(edges, "input")).toEqual([]);
  });

  it("suggests escaped field paths from the input schema", () => {
    const schema = {
      properties: { ticket: { properties: { id: {}, "a/b": {} } }, urgent: {} },
    };
    expect(inputFieldHints(schema)).toEqual([
      "/ticket",
      "/ticket/id",
      "/ticket/a~1b",
      "/urgent",
    ]);
    expect(inputFieldHints({ type: "object" })).toEqual([]);
  });

  it("summarises configured nodes for the canvas", () => {
    expect(
      configSummary(
        node("condition", {
          operator: "eq",
          left: { kind: "input", pointer: "/urgent" },
          right: { kind: "literal", value: true },
        }),
      ),
    ).toBe("/urgent equals true");
    expect(
      configSummary(
        node("condition", {
          operator: "exists",
          left: { kind: "input", pointer: "/a" },
          right: { kind: "literal", value: null },
        }),
      ),
    ).toBe("/a exists");
    expect(
      configSummary(node("tool", { tool_key: "text.replace" }), {
        "text.replace": "Replace text",
      }),
    ).toBe("Replace text");
    expect(configSummary(node("result", {}))).toBe("Returns the incoming data");
    expect(configSummary(node("manual_input", {}))).toBeNull();
    expect(templatePlaceholders("Hi {{/name}}, ticket {{/id}}")).toEqual([
      "/name",
      "/id",
    ]);
  });

  it("finds the step outputs a result reads and spots reshaping mappings", () => {
    const fields = node("result", {
      fields: {
        a: { kind: "output", node_id: "shape", pointer: "/x" },
        b: { kind: "output", node_id: "shape" },
        c: { kind: "input", pointer: "/y" },
      },
    });
    expect(resultSources(fields)).toEqual(["shape"]);
    expect(
      resultSources(
        node("result", { value: { kind: "output", node_id: "input" } }),
      ),
    ).toEqual(["input"]);
    expect(resultSources(node("result", {}))).toEqual([]);
    expect(configSummary(fields)).toBe("Returns { a, b, c }");
    expect(reshapes([{ from: "", to: "" }])).toBe(false);
    expect(reshapes([{ from: "/a", to: "/b" }])).toBe(true);
  });
});
