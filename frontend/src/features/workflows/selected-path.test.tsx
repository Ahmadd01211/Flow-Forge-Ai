import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import type { Graph, GraphNode, NodeTestResult } from "@/lib/api/types";
import { NodeTestPanel } from "./node-test-panel";

import {
  WorkflowConsole,
  type WorkflowExecution,
} from "../executions/workflow-console";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ refresh: () => {} }),
}));
const node = {
  id: "route",
  type: "switch",
  label: "Route",
  config: {
    value: { kind: "input", pointer: "/priority" },
    cases: [{ id: "urgent", label: "Urgent tickets", value: true }],
  },
  position: { x: 0, y: 0 },
  join: "all",
  policy: {},
} as GraphNode;
const graph = { nodes: [node], edges: [] } as unknown as Graph;

describe("selected paths in results", () => {
  it("shows the Switch label and stable port in a node test result", () => {
    const result: NodeTestResult = {
      node_id: "route",
      type: "switch",
      status: "completed",
      output: { priority: true },
      selected_port: "urgent",
      duration_ms: 1,
      external: false,
      error: null,
      agent_run: null,
    };
    const html = renderToStaticMarkup(
      <NodeTestPanel
        workspaceId="w"
        workflowId="f"
        graph={graph}
        node={node}
        tests={{ route: { result, configKey: JSON.stringify(node.config) } }}
        setTest={() => {}}
        sampleInput="{}"
        blocked={null}
        externalTarget={null}
      />,
    );
    expect(html).toContain("Urgent tickets path (urgent)");
  });
  it("includes the selected case and default in draft preview evidence", async () => {
    const { PreviewSteps } = await import("./workflow-preview");
    const html = renderToStaticMarkup(
      <PreviewSteps
        nodes={[node]}
        steps={[
          { node_id: "route", status: "completed", selected_port: "urgent" },
          { node_id: "route", status: "completed", selected_port: "default" },
        ]}
      />,
    );
    expect(html).toContain("Urgent tickets path (urgent)");
    expect(html).toContain("Default path (default)");
  });
  it("shows the stable Switch port in durable trace when definitions are unavailable", () => {
    const run: WorkflowExecution = {
      id: "run",
      workspace_id: "w",
      version_id: "v",
      automation_id: null,
      deployment_id: null,
      cancel_requested: false,
      cost_usd: null,
      created_at: "2026-11-11T10:00:00Z",
      error_code: null,
      finished_at: "2026-11-11T10:01:00Z",
      input_tokens: null,
      output: {},
      output_tokens: null,
      requested_by: "u",
      reserved_max_usd: "0",
      source: "manual",
      started_at: "2026-11-11T10:00:00Z",
      state: "completed",
      uncertain_cost_usd: null,
      steps: [
        {
          node_id: "route",
          type: "switch",
          status: "completed",
          output: {},
          selected_port: "urgent",
          attempt: 1,
          duration_ms: 1,
        },
      ],
    };
    const html = renderToStaticMarkup(
      <WorkflowConsole
        workspaceId="w"
        initial={[run]}
        canRun
        canReview
        userId="u"
      />,
    );
    expect(html).toContain("urgent path");
  });
});
