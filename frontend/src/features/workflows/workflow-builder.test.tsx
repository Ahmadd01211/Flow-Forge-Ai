// @vitest-environment jsdom
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import {
  act,
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
    if (url.endsWith("/preview"))
      return Response.json({ output: {}, steps: [] });
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
const mount = (draft: Graph = graph, canEdit = true, recipeSample?: import("@/features/templates/recipe-handoff").RecipeSample) =>
  render(
    <WorkflowBuilder
      recipeSample={recipeSample}
      workflow={{ ...workflow, graph: draft }}
      agentOptions={[]}
      mcpOptions={[]}
      httpOptions={[]}
      workflowOptions={[]}
      toolOptions={[]}
      connections={[]}
      canEdit={canEdit}
      initialPublishedVersion={null}
    />,
  );

describe("Switch builder integration", () => {
  it("initializes source sample and expected example without changing the graph or running", () => {
    const fetch = vi.spyOn(globalThis, "fetch");
    mount(graph, true, {sampleInput: {items: ["Ada", "Ada"]}, expectedResult: "One Ada remains."});
    expect(JSON.parse((screen.getByLabelText("Input JSON") as HTMLTextAreaElement).value)).toEqual({items: ["Ada", "Ada"]});
    expect(screen.getByText("Expected example: One Ada remains.")).toBeTruthy();
    expect(screen.getAllByText("Routing workflow").length).toBeGreaterThan(0);
    expect(saved).toBeUndefined();
    expect(fetch).not.toHaveBeenCalled();
    fireEvent.change(screen.getByLabelText("Input JSON"), {target: {value: '{"items":[]}'}});
    expect((screen.getByLabelText("Input JSON") as HTMLTextAreaElement).value).toBe('{"items":[]}');
  });
  it("asks for safe input when recipe metadata is absent", () => {
    mount();
    expect((screen.getByLabelText("Input JSON") as HTMLTextAreaElement).value).toBe("{}");
    expect(screen.getByText(/enter safe sample input/i)).toBeTruthy();
  });
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
    fireEvent.click(screen.getByRole("button", { name: "Check setup" }));
    await waitFor(() =>
      expect(screen.getByText("Setup checked.")).toBeTruthy(),
    );
    fireEvent.click(screen.getByRole("button", { name: "Preview" }));
    await waitFor(() =>
      expect(screen.getByText("Sample succeeded")).toBeTruthy(),
    );
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

it("shows a local launch checklist and opening sample controls never runs anything", async () => {
  mount();
  const checklist = screen.getByRole("region", { name: "Launch checklist" });
  expect(checklist.textContent).toContain("Not tested in this session");
  fireEvent.click(screen.getByRole("button", { name: "Check setup" }));
  await waitFor(() =>
    expect(checklist.textContent).toContain("Setup checked."),
  );
  fireEvent.click(screen.getByRole("button", { name: "Try a sample" }));
  expect(screen.getByLabelText("Input JSON")).toBeTruthy();
  expect(checklist.textContent).toContain("Not tested in this session");
});

it("local preview records only sample evidence and invalidates it after an edit", async () => {
  const original = fetch;
  const calls: string[] = [];
  vi.stubGlobal("fetch", async (url: string, options?: RequestInit) => {
    calls.push(url);
    if (url.endsWith("/preview"))
      return Response.json({ output: { count: 1, removed: 1 }, steps: [] });
    return original(url, options);
  });
  const local = structuredClone(graph);
  local.nodes[1] = {
    ...local.nodes[1],
    type: "list_deduplicate",
    label: "Remove duplicate contacts",
    config: { items: { kind: "input", pointer: "/items" }, key: "/email" },
  };
  local.edges = [local.edges[0], { ...local.edges[1], source_port: "out" }];
  mount(local);
  fireEvent.click(screen.getByRole("button", { name: "Check setup" }));
  await waitFor(() => expect(screen.getByText("Setup checked.")).toBeTruthy());
  fireEvent.click(screen.getByRole("button", { name: "Preview" }));
  await waitFor(() =>
    expect(screen.getByText("Sample succeeded")).toBeTruthy(),
  );
  expect(calls.some((url) => url.endsWith("/workflow-runs"))).toBe(false);
  expect(
    screen.getByRole("button", { name: "Publish a version" }),
  ).toBeTruthy();
  fireEvent.click(screen.getByTitle(/Add Switch/));
  expect(screen.queryByText("Sample succeeded")).toBeNull();
  expect(screen.queryByText("Setup checked.")).toBeNull();
});

it("external workflow opens sample input without running, then tracks waiting and matching completion", async () => {
  const original = fetch;
  const calls: string[] = [];
  let state = "waiting";
  let version = 0;
  vi.stubGlobal("fetch", async (url: string, options?: RequestInit) => {
    calls.push(url);
    if (url.endsWith("/versions"))
      return Response.json({ id: `version-${++version}`, number: version });
    if (url.endsWith("/workflow-runs"))
      return Response.json({ id: "run-1", state, output: {}, steps: [] });
    return original(url, options);
  });
  const external = structuredClone(graph);
  external.nodes[1] = {
    ...external.nodes[1],
    type: "llm",
    config: { provider: "openai", model_id: "test" },
  };
  mount(external);
  const titles = Array.from(
    screen
      .getByRole("region", { name: "Launch checklist" })
      .querySelectorAll("summary strong"),
  ).map((item) => item.textContent);
  expect(titles).toEqual([
    "Save your draft",
    "Check setup",
    "Publish a version",
    "Try a sample",
  ]);
  expect(
    (
      screen.getByRole("button", {
        name: "Run",
      }) as HTMLButtonElement
    ).disabled,
  ).toBe(true);
  fireEvent.click(screen.getByRole("button", { name: "Check setup" }));
  await waitFor(() => expect(screen.getByText("Setup checked.")).toBeTruthy());
  fireEvent.click(screen.getByRole("button", { name: "Publish a version" }));
  await waitFor(() =>
    expect(screen.getByText(/Current saved version published/)).toBeTruthy(),
  );
  fireEvent.click(screen.getByRole("button", { name: "Try a sample" }));
  expect(calls.some((url) => url.endsWith("/workflow-runs"))).toBe(false);
  fireEvent.click(screen.getByRole("button", { name: "Run" }));
  await waitFor(() =>
    expect(screen.getByText("Waiting for approval")).toBeTruthy(),
  );
  expect(screen.queryByText("Sample succeeded")).toBeNull();
  state = "completed";
  fireEvent.click(screen.getByRole("button", { name: "Run" }));
  await waitFor(() =>
    expect(screen.getByText("Sample succeeded")).toBeTruthy(),
  );
});

it("ignores setup responses after editing away and returning, and reveals unknown diagnostics", async () => {
  const original = fetch;
  let resolveCheck!: (response: Response) => void;
  vi.stubGlobal("fetch", async (url: string, options?: RequestInit) => {
    if (url.endsWith("/validate"))
      return new Promise<Response>((resolve) => {
        resolveCheck = resolve;
      });
    return original(url, options);
  });
  mount();
  fireEvent.click(screen.getByRole("button", { name: "Check setup" }));
  await waitFor(() => expect(resolveCheck).toBeDefined());
  fireEvent.click(screen.getByTitle(/Add Switch/));
  fireEvent.click(screen.getByTitle("Undo last graph edit"));
  resolveCheck(
    Response.json({ valid: true, publishable: true, errors: [], warnings: [] }),
  );
  await waitFor(() =>
    expect(
      (
        screen.getByRole("button", {
          name: "Validate",
        }) as HTMLButtonElement
      ).disabled,
    ).toBe(false),
  );
  expect(screen.queryByText("Setup checked.")).toBeNull();
  vi.stubGlobal("fetch", async (url: string, options?: RequestInit) =>
    url.endsWith("/validate")
      ? Response.json({
          valid: false,
          publishable: false,
          errors: [
            {
              code: "future",
              node_id: "missing",
              message: "Unknown node issue",
            },
            {
              code: "known",
              node_id: "route",
              message: "Routing needs attention",
            },
          ],
          warnings: [],
        })
      : original(url, options),
  );
  fireEvent.click(screen.getByRole("button", { name: "Check setup" }));
  await waitFor(() =>
    expect(
      screen.getByRole("button", { name: "Review issue: Unknown node issue" }),
    ).toBeTruthy(),
  );
  fireEvent.click(
    screen.getByRole("button", { name: "Review issue: Unknown node issue" }),
  );
  await waitFor(() =>
    expect(document.activeElement?.getAttribute("aria-label")).toBe(
      "Workflow validation",
    ),
  );
  fireEvent.click(
    screen.getByRole("button", {
      name: "Review issue: Routing needs attention",
    }),
  );
  expect(screen.getByRole("heading", { name: "Workflow steps" })).toBeTruthy();
  expect(
    document.querySelector(".accessible-node-list .selected")?.textContent,
  ).toContain("Routing");
});

it("does not validate after a failed save-and-check", async () => {
  const original = fetch;
  const calls: string[] = [];
  vi.stubGlobal("fetch", async (url: string, options?: RequestInit) => {
    calls.push(url);
    if (options?.method === "PATCH")
      return Response.json(
        { error: { message: "Save failed" } },
        { status: 500 },
      );
    return original(url, options);
  });
  mount();
  fireEvent.click(screen.getByTitle(/Add Switch/));
  fireEvent.click(screen.getByRole("button", { name: "Save & validate" }));
  await waitFor(() => expect(screen.getByText("Save failed")).toBeTruthy());
  expect(calls.some((url) => url.endsWith("/validate"))).toBe(false);
  expect(screen.queryByText("Setup checked.")).toBeNull();
});

it("protects viewer actions without issuing mutation requests", () => {
  mount(graph, false);
  expect(
    (screen.getByRole("button", { name: "Check setup" }) as HTMLButtonElement)
      .disabled,
  ).toBe(true);
  expect(
    (screen.getByRole("button", { name: "Validate" }) as HTMLButtonElement)
      .disabled,
  ).toBe(true);
  expect(screen.getByText(/You have read-only access/)).toBeTruthy();
});

it("ignores a preview that finishes after graph edits", async () => {
  const original = fetch;
  let finish!: (response: Response) => void;
  vi.stubGlobal("fetch", async (url: string, options?: RequestInit) =>
    url.endsWith("/preview")
      ? new Promise<Response>((resolve) => {
          finish = resolve;
        })
      : original(url, options),
  );
  mount();
  fireEvent.click(screen.getByRole("button", { name: "Check setup" }));
  await waitFor(() => expect(screen.getByText("Setup checked.")).toBeTruthy());
  fireEvent.click(screen.getByRole("button", { name: "Preview" }));
  await waitFor(() => expect(finish).toBeDefined());
  fireEvent.click(screen.getByTitle(/Add Switch/));
  finish(Response.json({ output: { stale: true }, steps: [] }));
  await waitFor(() =>
    expect(
      (
        screen.getByRole("button", {
          name: "Save & validate",
        }) as HTMLButtonElement
      ).disabled,
    ).toBe(false),
  );
  expect(screen.queryByText("Sample succeeded")).toBeNull();
});

it("leaves polling expiry unknown rather than successful", async () => {
  const original = fetch;
  vi.stubGlobal("fetch", async (url: string, options?: RequestInit) => {
    if (url.endsWith("/versions"))
      return Response.json({ id: "version-1", number: 1 });
    if (url.includes("/workflow-runs"))
      return Response.json({
        id: "run-1",
        state: "running",
        output: {},
        steps: [],
      });
    return original(url, options);
  });
  const external = structuredClone(graph);
  external.nodes[1] = {
    ...external.nodes[1],
    type: "llm",
    config: { provider: "openai", model_id: "test" },
  };
  mount(external);
  fireEvent.click(screen.getByRole("button", { name: "Check setup" }));
  await waitFor(() => expect(screen.getByText("Setup checked.")).toBeTruthy());
  fireEvent.click(screen.getByRole("button", { name: "Publish a version" }));
  await waitFor(() =>
    expect(screen.getByText(/Current saved version published/)).toBeTruthy(),
  );
  vi.useFakeTimers();
  try {
    fireEvent.click(screen.getByRole("button", { name: "Run" }));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(36000);
    });
    expect(screen.getByText("Sample status unknown")).toBeTruthy();
    expect(screen.queryByText("Sample succeeded")).toBeNull();
  } finally {
    vi.useRealTimers();
  }
});

it.each(["queued", "running"])(
  "retains an accepted %s run as unknown when status polling fails",
  async (state) => {
    const original = fetch;
    vi.stubGlobal("fetch", async (url: string, options?: RequestInit) => {
      if (url.endsWith("/versions"))
        return Response.json({ id: "version-1", number: 1 });
      if (url.endsWith("/workflow-runs") && options?.method === "POST")
        return Response.json({
          id: "accepted-workflow-run",
          state,
          output: null,
          steps: null,
          error_code: null,
          cost_usd: null,
          uncertain_cost_usd: null,
          input_tokens: null,
          output_tokens: null,
        });
      if (url.endsWith("/workflow-runs/accepted-workflow-run"))
        throw new Error("Status connection lost");
      return original(url, options);
    });
    const external = structuredClone(graph);
    external.nodes[1] = {
      ...external.nodes[1],
      type: "llm",
      config: { provider: "openai", model_id: "test" },
    };
    mount(external);
    fireEvent.click(screen.getByRole("button", { name: "Check setup" }));
    await waitFor(() => expect(screen.getByText("Setup checked.")).toBeTruthy());
    fireEvent.click(screen.getByRole("button", { name: "Publish a version" }));
    await waitFor(() =>
      expect(screen.getByText(/Current saved version published/)).toBeTruthy(),
    );
    vi.useFakeTimers();
    try {
      fireEvent.click(screen.getByRole("button", { name: "Run" }));
      await act(async () => vi.advanceTimersByTimeAsync(1000));
      expect(screen.getByText("Sample status unknown")).toBeTruthy();
      expect(screen.queryByText("Sample failed")).toBeNull();
      expect(
        screen.getByRole("link", { name: "Open durable step debugger" }).getAttribute("href"),
      ).toBe("/w/w/executions?kind=workflows&runId=accepted-workflow-run");
      expect(screen.getByText("Status connection lost")).toBeTruthy();
    } finally {
      vi.useRealTimers();
    }
  },
);

it("discards a durable completion after editing the running graph", async () => {
  const original = fetch;
  let finish!: (response: Response) => void;
  vi.stubGlobal("fetch", async (url: string, options?: RequestInit) => {
    if (url.endsWith("/versions"))
      return Response.json({ id: "v1", number: 1 });
    if (url.endsWith("/workflow-runs"))
      return new Promise<Response>((resolve) => {
        finish = resolve;
      });
    return original(url, options);
  });
  const external = structuredClone(graph);
  external.nodes[1] = {
    ...external.nodes[1],
    type: "llm",
    config: { provider: "openai", model_id: "test" },
  };
  mount(external);
  fireEvent.click(screen.getByRole("button", { name: "Check setup" }));
  await waitFor(() => expect(screen.getByText("Setup checked.")).toBeTruthy());
  fireEvent.click(screen.getByRole("button", { name: "Publish a version" }));
  await waitFor(() =>
    expect(screen.getByText(/Current saved version published/)).toBeTruthy(),
  );
  fireEvent.click(screen.getByRole("button", { name: "Run" }));
  await waitFor(() => expect(finish).toBeDefined());
  fireEvent.click(screen.getByTitle(/Add Switch/));
  finish(
    Response.json({ id: "run1", state: "completed", output: {}, steps: [] }),
  );
  await waitFor(() =>
    expect(
      (
        screen.getByRole("button", {
          name: "Save & validate",
        }) as HTMLButtonElement
      ).disabled,
    ).toBe(false),
  );
  expect(screen.queryByText("Sample succeeded")).toBeNull();
});

it("invalidates session sample and setup evidence after returning to the tab", async () => {
  mount();
  fireEvent.click(screen.getByRole("button", { name: "Check setup" }));
  await waitFor(() => expect(screen.getByText("Setup checked.")).toBeTruthy());
  fireEvent.click(screen.getByRole("button", { name: "Preview" }));
  await waitFor(() =>
    expect(screen.getByText("Sample succeeded")).toBeTruthy(),
  );
  Object.defineProperty(document, "visibilityState", {
    configurable: true,
    value: "hidden",
  });
  fireEvent(document, new Event("visibilitychange"));
  Object.defineProperty(document, "visibilityState", {
    configurable: true,
    value: "visible",
  });
  fireEvent(document, new Event("visibilitychange"));
  expect(screen.queryByText("Setup checked.")).toBeNull();
  expect(screen.queryByText("Sample succeeded")).toBeNull();
  expect(screen.getByText("Not tested in this session")).toBeTruthy();
});

it("rejects preview evidence when edits and undo happen during its save", async () => {
  const original = fetch;
  let finishSave!: (response: Response) => void;
  let submitted: { name: string; graph: Graph };
  const previews: string[] = [];
  vi.stubGlobal("fetch", async (url: string, options?: RequestInit) => {
    if (options?.method === "PATCH") {
      submitted = JSON.parse(String(options.body));
      return new Promise<Response>((resolve) => {
        finishSave = resolve;
      });
    }
    if (url.endsWith("/preview")) previews.push(url);
    return original(url, options);
  });
  mount();
  fireEvent.click(screen.getByTitle(/Add Switch/));
  fireEvent.click(screen.getByRole("button", { name: "Preview" }));
  await waitFor(() => expect(finishSave).toBeDefined());
  fireEvent.click(screen.getByTitle(/Add Switch/));
  fireEvent.click(screen.getByTitle("Undo last graph edit"));
  finishSave(Response.json({ ...workflow, ...submitted!, revision: 2 }));
  await waitFor(() =>
    expect(
      (screen.getByRole("button", { name: "Validate" }) as HTMLButtonElement)
        .disabled,
    ).toBe(false),
  );
  fireEvent.click(screen.getByRole("button", { name: "Check setup" }));
  await waitFor(() => expect(screen.getByText("Setup checked.")).toBeTruthy());
  expect(screen.queryByText("Sample succeeded")).toBeNull();
  expect(previews).toHaveLength(0);
  expect(screen.getByText("Not tested in this session")).toBeTruthy();
});

it("shows normal checking punctuation while the explicit check is pending", async () => {
  const original = fetch;
  let finish!: (response: Response) => void;
  vi.stubGlobal("fetch", async (url: string, options?: RequestInit) =>
    url.endsWith("/validate")
      ? new Promise<Response>((resolve) => {
          finish = resolve;
        })
      : original(url, options),
  );
  mount();
  fireEvent.click(screen.getByRole("button", { name: "Check setup" }));
  await waitFor(() => expect(finish).toBeDefined());
  expect(screen.getByText("Checking setup...")).toBeTruthy();
  finish(
    Response.json({ valid: true, publishable: true, errors: [], warnings: [] }),
  );
  await waitFor(() => expect(screen.getByText("Setup checked.")).toBeTruthy());
});
