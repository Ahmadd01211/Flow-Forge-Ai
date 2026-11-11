import { describe, expect, it } from "vitest";
import { activityLabel, attentionItems, barHeights, duration, money, runHref, setupSteps, type OverviewData } from "./overview-model";

const base = "/w/ws";
const withAttention = (overrides: Partial<OverviewData["attention"]> = {}): OverviewData =>
  ({
    attention: {
      approvals: [], approvals_total: 0, failed_runs_24h: 0, stale_agents: [], trigger_errors: [],
      near_limits: { spend: false, runs: false, spend_ratio: 0, run_ratio: 0 }, ...overrides,
    },
  }) as unknown as OverviewData;

describe("overview helpers", () => {
  it("turns problems into actionable attention items", () => {
    expect(attentionItems(withAttention(), base)).toEqual([]);
    const items = attentionItems(withAttention({
      failed_runs_24h: 1,
      stale_agents: [{ agent_id: "a1", name: "Triage", version_number: 3, reason: "credential_changed" }],
      trigger_errors: [{ id: "t1", name: "Nightly", kind: "schedule", last_error_code: "RUN_CONCURRENCY_LIMIT" }],
      near_limits: { spend: true, runs: false, spend_ratio: 0.85, run_ratio: 0.2 },
    }), base);
    expect(items.map((item) => [item.tone, item.href])).toEqual([
      ["critical", "/w/ws/executions?kind=workflows"],
      ["critical", "/w/ws/agents/a1"],
      ["warning", "/w/ws/automations"],
      ["warning", "/w/ws/usage"],
    ]);
    expect(items[0].text).toBe("1 failed run in the last 24 hours");
    expect(items[3].text).toBe("85% of today's budget is committed");
  });

  it("keeps the teammate step optional and links each setup step", () => {
    const steps = setupSteps({ provider_connected: true, published: false, succeeded: false, trigger: false, teammates: false, complete: false }, base);
    expect(steps.filter((step) => !step.optional).map((step) => step.done)).toEqual([true, false, false, false]);
    expect(steps.at(-1)?.optional).toBe(true);
  });

  it("formats labels, money, durations, links and bar heights", () => {
    expect(activityLabel("workflow.published")).toBe("published a workflow");
    expect(activityLabel("something.new_thing")).toBe("something new thing");
    expect(money("0.0042")).toBe("$0.0042");
    expect(money("12")).toBe("$12.00");
    expect(duration(null)).toBe("—");
    expect(duration(4.25)).toBe("4.3s");
    expect(duration(125)).toBe("2m 5s");
    expect(runHref({ kind: "workflow", id: "r1" } as OverviewData["recent_runs"][number], base)).toBe("/w/ws/executions?kind=workflows&runId=r1");
    expect(barHeights([0, 0])).toEqual([0, 0]);
    expect(barHeights([0, 1, 50, 100])).toEqual([0, 4, 50, 100]);
  });
});
