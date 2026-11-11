import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { RunTrace } from "./run-trace";
import type { TraceData } from "./trace-model";

function trace(mayDecide: boolean): TraceData {
  return {
    run: {
      id: "run-1", state: "waiting", output: null, error_code: null,
      cost_usd: null, uncertain_cost_usd: null, input_tokens: 30, output_tokens: 8,
      created_at: "2026-11-11T10:00:00Z", started_at: "2026-11-11T10:00:00Z", finished_at: null,
    },
    input: { ticket: "example" },
    agent: {
      id: "agent-1", workflow_id: null, name: "Billing assistant", version_number: 2,
      provider: "openai", model_id: "gpt-5-mini", playground: false, skills: [], source: "manual",
    },
    steps: [],
    totals: { duration_ms: null, model_calls: 1, tool_calls: 1 },
    feedback: { up: 0, down: 0, mine: null, comments: [] },
    tool_approval: {
      id: "approval-1", state: "pending", tool_key: "mcp:billing/create_customer",
      tool: {
        server_id: "billing", server_name: "Billing", tool_name: "create_customer",
        description: "Creates a customer record", read_only: false,
      },
      arguments: { customer_id: "cus_safe_123" },
      requester: { id: "requester-1", name: "Alex" },
      deployment: { id: "deployment-1", name: "Support production" },
      expires_at: "2026-11-12T10:00:00Z", decided_at: null, decided_by: null,
      may_decide: mayDecide,
    },
  };
}

describe("RunTrace tool approval panel", () => {
  it("shows exact arguments and withholds actions from the requester", () => {
    const markup = renderToStaticMarkup(
      <RunTrace workspaceId="workspace-1" trace={trace(false)} canEdit />,
    );

    expect(markup).toContain("waiting for approval");
    expect(markup).toContain("Write action");
    expect(markup).toContain("cus_safe_123");
    expect(markup).toContain("Support production");
    expect(markup).toContain("different workspace owner or admin");
    expect(markup).not.toContain("Approve and continue");
  });

  it("shows approve and reject controls only when the server grants them", () => {
    const markup = renderToStaticMarkup(
      <RunTrace workspaceId="workspace-1" trace={trace(true)} canEdit />,
    );

    expect(markup).toContain("Approve and continue");
    expect(markup).toContain("Reject call");
  });
});
