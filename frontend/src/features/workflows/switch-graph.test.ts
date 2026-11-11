import { describe, expect, it } from "vitest";
import type { Edge } from "@xyflow/react";
import type { GraphNode } from "@/lib/api/types";
import { outputPorts, selectedPathLabel } from "./node-config";
import { edgesAfterConfigEdit, serializeEdges } from "./graph-edit";

const node = {
  id: "route",
  type: "switch",
  label: "Route",
  position: { x: 0, y: 0 },
  join: "all",
  policy: {},
  config: {
    value: { kind: "input", pointer: "/priority" },
    cases: [
      { id: "urgent", label: "Urgent tickets", value: true },
      { id: "normal", label: "Normal tickets", value: 1 },
    ],
  },
} as GraphNode;
const edges: Edge[] = [
  {
    id: "urgent-edge",
    source: "route",
    sourceHandle: "urgent",
    target: "a",
    data: { mappings: [{ from: "/x", to: "/y" }] },
  },
  { id: "normal-edge", source: "route", sourceHandle: "normal", target: "a" },
  { id: "fallback", source: "route", sourceHandle: "default", target: "a" },
  { id: "other", source: "other", sourceHandle: "urgent", target: "a" },
];

describe("Switch graph editing", () => {
  it("keeps case IDs and the default visible after label edits and reordering", () => {
    const config = {
      ...node.config,
      cases: [
        { id: "normal", label: "Renamed", value: 1 },
        { id: "urgent", label: "Urgent tickets", value: true },
      ],
    };
    expect(outputPorts({ ...node, config })).toEqual([
      { id: "normal", label: "Renamed" },
      { id: "urgent", label: "Urgent tickets" },
      { id: "default", label: "Default" },
    ]);
    expect(edgesAfterConfigEdit(edges, node, config)).toEqual(edges);
  });
  it("removes only a deleted case edge and retains default and other sources", () => {
    const edited = edgesAfterConfigEdit(edges, node, {
      ...node.config,
      cases: [{ id: "normal", label: "Normal", value: 1 }],
    });
    expect(edited.map((e) => e.id)).toEqual([
      "normal-edge",
      "fallback",
      "other",
    ]);
    expect(edgesAfterConfigEdit(edges, node, {})).toEqual(edges);
    expect(edgesAfterConfigEdit(edges, node, { cases: [null] })).toEqual(edges);
  });
  it("serializes stable case/default IDs and mappings and legacy condition ports", () => {
    expect(
      serializeEdges([
        ...edges,
        { id: "legacy", source: "if", sourceHandle: "false", target: "a" },
      ]),
    ).toEqual([
      {
        id: "urgent-edge",
        source: "route",
        source_port: "urgent",
        target: "a",
        target_port: "in",
        mappings: [{ from: "/x", to: "/y" }],
      },
      {
        id: "normal-edge",
        source: "route",
        source_port: "normal",
        target: "a",
        target_port: "in",
        mappings: [],
      },
      {
        id: "fallback",
        source: "route",
        source_port: "default",
        target: "a",
        target_port: "in",
        mappings: [],
      },
      {
        id: "other",
        source: "other",
        source_port: "urgent",
        target: "a",
        target_port: "in",
        mappings: [],
      },
      {
        id: "legacy",
        source: "if",
        source_port: "false",
        target: "a",
        target_port: "in",
        mappings: [],
      },
    ]);
  });
  it("shows a selected Switch label and stable ID with type-aware path wording", () => {
    expect(selectedPathLabel("urgent", node)).toBe(
      "Urgent tickets path (urgent)",
    );
    expect(selectedPathLabel("default", node)).toBe("Default path (default)");
    expect(selectedPathLabel("gone", node)).toBe("gone path");
    expect(selectedPathLabel("false", { ...node, type: "condition" })).toBe(
      "false path",
    );
    expect(selectedPathLabel("urgent")).toBe("urgent path");
  });
});
