export type LaunchAction =
  "save" | "check" | "configure" | "sample" | "publish" | "result";
export type LaunchMode = "agent_test" | "local_preview" | "published_run";
export type LaunchIssue = { code: string; message: string; target?: string };
export type SampleEvidence = {
  requestId: string;
  configKey: string;
  inputKey: string;
  mode: LaunchMode;
  state:
    "running" | "waiting" | "completed" | "failed" | "cancelled" | "unknown";
  runId?: string;
  versionId?: string;
};
export type LaunchFacts = {
  mode: LaunchMode;
  saved: boolean;
  dirty: boolean;
  canEdit: boolean;
  configKey: string;
  latestRequestId: string | null;
  check:
    "unchecked" | "checking" | "failed" | "blocked" | "passed" | "setup_only";
  issues: LaunchIssue[];
  warnings: LaunchIssue[];
  publishedCurrent: boolean;
  publishedVersionId: string | null;
  sample: SampleEvidence | null;
};
export type LaunchStep = {
  id: "save" | "check" | "sample" | "publish";
  title: string;
  status: "pending" | "working" | "blocked" | "complete";
  description: string;
  action: LaunchAction | null;
};
/** In-memory equality key for JSON definitions; never pass credentials or run output. */
export function launchConfigKey(value: unknown): string {
  return (
    JSON.stringify(value, (_key, item) =>
      item && typeof item === "object" && !Array.isArray(item)
        ? Object.fromEntries(
            Object.keys(item)
              .sort()
              .map((key) => [key, item[key]]),
          )
        : item,
    ) ?? "undefined"
  );
}
export function deriveLaunchSteps(facts: LaunchFacts): LaunchStep[] {
  const clean = facts.saved && !facts.dirty;
  const checked = facts.check === "passed";
  const publishable =
    clean &&
    (checked || facts.check === "setup_only") &&
    facts.issues.length === 0;
  const published = clean && facts.publishedCurrent;
  const save: LaunchStep = {
    id: "save",
    title: "Save your draft",
    status: clean ? "complete" : "pending",
    description: clean
      ? "Draft saved."
      : "Save your changes before checking setup or publishing.",
    action: clean ? null : "save",
  };
  const check: LaunchStep = {
    id: "check",
    title: "Check setup",
    status: !clean
      ? "pending"
      : facts.check === "checking"
        ? "working"
        : facts.check === "passed" || facts.check === "setup_only"
          ? "complete"
          : facts.check === "blocked" || facts.check === "failed"
            ? "blocked"
            : "pending",
    description: !clean
      ? "Save and check setup"
      : facts.check === "checking"
        ? "Checking setup..."
        : facts.check === "passed"
          ? "Setup checked."
          : facts.check === "setup_only"
            ? "Setup can be published, but this model cannot run samples."
            : facts.check === "failed"
              ? "Setup check could not be completed. Try again."
              : facts.check === "blocked"
                ? "Resolve the setup issues below."
                : "Setup has not been checked.",
    action: facts.check === "checking" && clean ? null : "check",
  };
  const publish: LaunchStep = {
    id: "publish",
    title: "Publish a version",
    status: published ? "complete" : publishable ? "pending" : "blocked",
    description: published
      ? "Current saved version published. Publishing does not run anything."
      : "Publishing creates a version and does not run anything. A sample is optional.",
    action: published ? null : publishable ? "publish" : null,
  };
  const durable = facts.mode === "published_run";
  const allowed =
    checked &&
    facts.issues.length === 0 &&
    (!durable || (published && !!facts.publishedVersionId));
  const evidence = facts.sample;
  const matches =
    allowed &&
    evidence &&
    evidence.configKey === facts.configKey &&
    evidence.requestId === facts.latestRequestId &&
    evidence.mode === facts.mode &&
    (!durable || evidence.versionId === facts.publishedVersionId);
  let status: LaunchStep["status"] = allowed ? "pending" : "blocked";
  let description =
    facts.check === "setup_only"
      ? "This model is setup only and cannot run samples."
      : durable && !published
        ? "Publish the current saved version before trying a sample."
        : "Not tested in this session";
  let action: LaunchAction | null = allowed ? "sample" : null;
  if (matches) {
    description = {
      completed: "Sample succeeded",
      failed: "Sample failed",
      running: "Still running",
      waiting: "Waiting for approval",
      cancelled: "Sample cancelled",
      unknown: "Sample status unknown",
    }[evidence.state];
    status =
      evidence.state === "completed"
        ? "complete"
        : evidence.state === "running" || evidence.state === "waiting"
          ? "working"
          : evidence.state === "failed"
            ? "blocked"
            : "pending";
    action = "result";
  }
  const sample: LaunchStep = {
    id: "sample",
    title: "Try a sample",
    status,
    description,
    action,
  };
  return durable
    ? [save, check, publish, sample]
    : [save, check, sample, publish];
}
