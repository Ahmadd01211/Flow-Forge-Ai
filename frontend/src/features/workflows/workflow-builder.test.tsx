// @vitest-environment jsdom
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { WorkflowBuilder } from "./workflow-builder";
import type { Graph, Workflow } from "@/lib/api/types";
// Read only in Vitest; the frontend Docker build does not include backend test artifacts.
const continuation = JSON.parse(
  readFileSync(
    resolve(
      process.cwd(),
      "../backend/tests/fixtures/builder-switch-continuation.json",
    ),
    "utf8",
  ),
) as Graph;

const graph: Graph = {
  schema_version: 1,
  input_schema: {},
  output_schema: {},
  limits: {},
  nodes: [
    {
      id: "input",
      type: "manual_input",
      label: "Input",
      config: {},
      position: { x: 0, y: 0 },
      join: "all",
      policy: {},
    },
    {
      id: "route",
      type: "switch",
      label: "Routing",
      config: {
        value: { kind: "input", pointer: "/priority" },
        cases: [
          { id: "urgent", label: "Urgent", value: true },
          { id: "normal", label: "Normal", value: 1 },
        ],
      },
      position: { x: 200, y: 0 },
      join: "all",
      policy: {},
    },
    {
      id: "result",
      type: "result",
      label: "Result",
      config: {},
      position: { x: 400, y: 0 },
      join: "active",
      policy: {},
    },
  ],
  edges: [
    {
      id: "incoming",
      source: "input",
      source_port: "out",
      target: "route",
      target_port: "in",
      mappings: [],
    },
    ...["urgent", "normal", "default"].map((source_port) => ({
      id: source_port,
      source: "route",
      source_port,
      target: "result",
      target_port: "in" as const,
      mappings: [],
    })),
  ],
};
const workflow: Workflow = {
  id: "flow",
  workspace_id: "w",
  name: "Routing workflow",
  description: "",
  graph,
  revision: 1,
  updated_at: "2026-11-11T00:00:00Z",
};
let saved: Graph | undefined;
beforeEach(() => {
  saved = undefined;
  vi.stubGlobal(
    "ResizeObserver",
    class {
      observe() {}
      unobserve() {}
      disconnect() {}
    },
  );
  // jsdom has no layout matrix API; these tests use the Steps view at unit zoom.
  vi.stubGlobal(
    "DOMMatrixReadOnly",
    class {
      m22 = 1;
    },
  );
  vi.stubGlobal("fetch", async (url: string, options?: RequestInit) => {
    if (url.endsWith("/csrf")) return Response.json({ csrf_token: "test" });
    if (options?.method === "PATCH") {
      saved = JSON.parse(String(options.body)).graph;
      return Response.json({ ...workflow, graph: saved, revision: 2 });
    }
    return Response.json({
      valid: true,
      publishable: true,
      errors: [],
      warnings: [],
      scope: "draft",
    });
  });
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});
const mount = (draft: Graph = graph) =>
  render(
    <WorkflowBuilder
      workflow={{ ...workflow, graph: draft }}
      agentOptions={[]}
      mcpOptions={[]}
      httpOptions={[]}
      workflowOptions={[]}
      toolOptions={[]}
      connections={[]}
      initialPublishedVersion={null}
    />,
  );

describe("Switch builder integration", () => {
  it("saves an executable continuation matching the backend preview fixture", async () => {
    const linear = structuredClone(continuation) as Graph;
    linear.nodes = linear.nodes.filter((node) => node.type !== "switch");
    linear.nodes.find((node) => node.id === "cleanup")!.join = "all";
    linear.edges = [
      {
        id: "incoming",
        source: "input",
        source_port: "out",
        target: "cleanup",
        target_port: "in",
        mappings: [],
      },
      {
        id: "outgoing",
        source: "cleanup",
        source_port: "out",
        target: "result",
        target_port: "in",
        mappings: [],
      },
    ];
    mount(linear);
    fireEvent.click(screen.getByTitle(/Add Switch/));
    fireEvent.change(screen.getByLabelText("Value to route field path"), {
      target: { value: "/route" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(saved).toBeDefined());
    const inserted = saved!.nodes.find((node) => node.type === "switch")!;
    const caseId = (inserted.config.cases as { id: string }[])[0].id;
    const stableId = (id: string) =>
      id === inserted.id
        ? "switch-inserted"
        : id === caseId
          ? "case-inserted"
          : id;
    const normalized = {
      ...saved,
      nodes: saved!.nodes.map((node) => ({
        ...node,
        id: stableId(node.id),
        position: { x: 0, y: 0 },
        config:
          node.type === "switch"
            ? {
                ...node.config,
                cases: (node.config.cases as { id: string }[]).map((item) => ({
                  ...item,
                  id: stableId(item.id),
                })),
              }
            : node.config,
      })),
      edges: saved!.edges.map((edge) => ({
        ...edge,
        source: stableId(edge.source),
        source_port: stableId(edge.source_port),
        target: stableId(edge.target),
        id: `${stableId(edge.source)}-${stableId(edge.source_port)}-${stableId(edge.target)}`,
      })),
    };
    // The backend test previews this same artifact for both matching and default routes.
    expect(normalized).toEqual(continuation);
  });
  it("keeps an unrelated all-join behind an explicit active-path merge", async () => {
    const draft = structuredClone(continuation) as Graph;
    draft.nodes = draft.nodes.filter((node) => node.type !== "switch");
    const cleanup = draft.nodes.find((node) => node.id === "cleanup")!;
    cleanup.type = "transform";
    cleanup.config = { fields: { joined: { kind: "literal", value: true } } };
    cleanup.join = "all";
    for (const id of ["lead", "other"])
      draft.nodes.push({
        ...structuredClone(cleanup),
        id,
        label: id === "lead" ? "Lead" : "Other",
      });
    draft.edges = [
      {
        id: "first",
        source: "input",
        source_port: "out",
        target: "lead",
        target_port: "in",
        mappings: [],
      },
      {
        id: "parallel",
        source: "input",
        source_port: "out",
        target: "other",
        target_port: "in",
        mappings: [],
      },
      {
        id: "incoming",
        source: "lead",
        source_port: "out",
        target: "cleanup",
        target_port: "in",
        mappings: [],
      },
      {
        id: "other",
        source: "other",
        source_port: "out",
        target: "cleanup",
        target_port: "in",
        mappings: [],
      },
      {
        id: "outgoing",
        source: "cleanup",
        source_port: "out",
        target: "result",
        target_port: "in",
        mappings: [],
      },
    ];
    mount(draft);
    fireEvent.click(screen.getByRole("button", { name: "Steps" }));
    fireEvent.click(screen.getByRole("button", { name: /Lead.*transform/ }));
    fireEvent.click(screen.getByTitle(/Add Switch/));
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(saved).toBeDefined());
    const inserted = saved!.nodes.find(
      (node) => node.type === "switch" && node.id !== "route",
    )!;
    const merge = saved!.nodes.find((node) => node.type === "merge")!;
    expect(merge?.config).toEqual({ mode: "active" });
    expect(saved!.nodes.find((node) => node.id === "cleanup")!.join).toBe(
      "all",
    );
    expect(
      saved!.edges
        .filter((edge) => edge.source === inserted.id)
        .map((edge) => edge.target),
    ).toEqual([merge.id, merge.id]);
    expect(saved!.edges.find((edge) => edge.source === merge.id)?.target).toBe(
      "cleanup",
    );
    expect(saved!.edges.find((edge) => edge.id === "other")?.source).toBe(
      "other",
    );
  });
  it("inserts a new Switch with stable case and default connections", async () => {
    mount();
    fireEvent.click(screen.getByTitle(/Add Switch/));
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(saved).toBeDefined());
    const added = saved!.nodes.find(
      (node) => node.type === "switch" && node.id !== "route",
    )!;
    const cases = added.config.cases as { id: string }[];
    expect(cases).toHaveLength(1);
    expect(cases[0].id).toMatch(/^case_[a-f0-9]{8}$/);
    expect(
      saved!.edges
        .filter((edge) => edge.source === added.id)
        .map((edge) => [edge.source_port, edge.target]),
    ).toEqual([
      [cases[0].id, "route"],
      ["default", "route"],
    ]);
    expect(saved!.edges.find((edge) => edge.id === "incoming")?.target).toBe(
      added.id,
    );
  });
  it("inserts Remove duplicates on the selected default path without changing other routes", async () => {
    mount();
    fireEvent.click(screen.getByRole("button", { name: "Steps" }));
    fireEvent.click(screen.getByRole("button", { name: /Routing.*switch/ }));
    fireEvent.change(screen.getByLabelText("Branch"), {
      target: { value: "default" },
    });
    fireEvent.click(screen.getByTitle(/Add Remove duplicates/));
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(saved).toBeDefined());
    const added = saved!.nodes.find(
      (node) => node.type === "list_deduplicate",
    )!;
    expect(added.config).toEqual({ source: "/items" });
    expect(
      saved!.edges
        .filter((edge) => edge.source === "route")
        .map((edge) => [edge.source_port, edge.target]),
    ).toEqual([
      ["urgent", "result"],
      ["normal", "result"],
      ["default", added.id],
    ]);
    expect(saved!.edges.find((edge) => edge.source === added.id)?.target).toBe(
      "result",
    );
  });
  it("offers both practical nodes and saves stable routes after renaming and deletion", async () => {
    mount();
    expect(screen.getByTitle(/Add Switch/)).toBeTruthy();
    expect(screen.getByTitle(/Add Remove duplicates/)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Steps" }));
    fireEvent.click(screen.getByRole("button", { name: /Routing.*switch/ }));
    fireEvent.change(screen.getByLabelText("Case 1 label"), {
      target: { value: "Renamed" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Move case 1 down" }));
    fireEvent.click(screen.getByRole("button", { name: "Remove case 1" }));
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(saved).toBeDefined());
    expect(
      saved?.nodes.find((node) => node.id === "route")?.config.cases,
    ).toEqual([{ id: "urgent", label: "Renamed", value: true }]);
    expect(
      saved?.edges
        .filter((edge) => edge.source === "route")
        .map((edge) => edge.source_port),
    ).toEqual(["urgent", "default"]);
    expect(saved?.edges.find((edge) => edge.id === "incoming")?.target).toBe(
      "route",
    );
  });
});
