import { expect, it } from "vitest";
import {
  deriveLaunchSteps,
  launchConfigKey,
  type LaunchFacts,
  type SampleEvidence,
} from "./launch-model";
const readyFacts: LaunchFacts = {
  mode: "agent_test",
  saved: true,
  dirty: false,
  canEdit: true,
  configKey: "current",
  latestRequestId: null,
  check: "passed",
  issues: [],
  warnings: [],
  publishedCurrent: false,
  publishedVersionId: null,
  sample: null,
};
const evidence: SampleEvidence = {
  requestId: "latest",
  configKey: "current",
  inputKey: "input",
  mode: "agent_test",
  state: "completed",
};
const sample = (overrides: Partial<LaunchFacts> = {}) =>
  deriveLaunchSteps({
    ...readyFacts,
    latestRequestId: "latest",
    sample: evidence,
    ...overrides,
  }).find((s) => s.id === "sample")!;
it("orders local and durable journeys", () => {
  expect(
    deriveLaunchSteps({ ...readyFacts, mode: "local_preview" }).map(
      (s) => s.id,
    ),
  ).toEqual(["save", "check", "sample", "publish"]);
  expect(
    deriveLaunchSteps({ ...readyFacts, mode: "published_run" }).map(
      (s) => s.id,
    ),
  ).toEqual(["save", "check", "publish", "sample"]);
});
it("only accepts the current submitted configuration, request and mode", () => {
  expect(sample().status).toBe("complete");
  for (const patch of [
    { configKey: "old" },
    { requestId: "old" },
    { mode: "local_preview" as const },
  ])
    expect(sample({ sample: { ...evidence, ...patch } }).status).not.toBe(
      "complete",
    );
  expect(sample({ latestRequestId: null }).status).not.toBe("complete");
  for (const state of [
    "failed",
    "waiting",
    "unknown",
    "cancelled",
    "running",
  ] as const)
    expect(sample({ sample: { ...evidence, state } }).status).not.toBe(
      "complete",
    );
});
it("requires a clean matching publication for durable sample evidence", () => {
  const facts = {
    ...readyFacts,
    mode: "published_run" as const,
    publishedCurrent: true,
    publishedVersionId: "v1",
    latestRequestId: "latest",
    sample: { ...evidence, mode: "published_run" as const, versionId: "v1" },
  };
  expect(sample(facts).status).toBe("complete");
  for (const patch of [
    { dirty: true },
    { publishedCurrent: false },
    { publishedVersionId: "v2" },
    { publishedVersionId: null },
  ])
    expect(sample({ ...facts, ...patch }).status).not.toBe("complete");
});
it("distinguishes pending checks, blockers and publishable setup-only models", () => {
  expect(
    deriveLaunchSteps({ ...readyFacts, check: "unchecked" })[1].status,
  ).toBe("pending");
  expect(
    deriveLaunchSteps({ ...readyFacts, check: "checking" })[1].status,
  ).toBe("working");
  const steps = deriveLaunchSteps({ ...readyFacts, check: "setup_only" });
  expect(steps.find((s) => s.id === "sample")?.status).toBe("blocked");
  expect(steps.find((s) => s.id === "publish")?.action).toBe("publish");
  expect(sample({ check: "failed" }).status).not.toBe("complete");
  expect(sample({ check: "unchecked" }).status).not.toBe("complete");
  expect(sample({ dirty: true }).status).toBe("complete");
});
it("serializes nested keys deterministically while preserving arrays and raw text", () => {
  expect(launchConfigKey({ b: { z: 2, a: 1 }, a: [1, 2] })).toBe(
    launchConfigKey({ a: [1, 2], b: { a: 1, z: 2 } }),
  );
  expect(launchConfigKey([1, 2])).not.toBe(launchConfigKey([2, 1]));
  expect(launchConfigKey({ schema: "{bad" })).not.toBe(
    launchConfigKey({ schema: "{bad " }),
  );
});
