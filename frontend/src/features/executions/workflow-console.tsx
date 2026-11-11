"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Clock3, RefreshCw, RotateCcw, Square } from "lucide-react";
import {
  Badge,
  EmptyState,
  ErrorNotice,
  PageHeader,
} from "@/components/shared/ui";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api/client";
import { LocalTime } from "@/components/shared/local-time";
import type { components } from "@/lib/api/generated";
import { selectedPathLabel } from "@/features/workflows/node-config";

export type WorkflowExecution = components["schemas"]["WorkflowRunRead"];
type StepDetail = components["schemas"]["WorkflowStepDetail"];
function stepLabel(step: {
  node_id: string;
  definition_node_id?: string | null;
  scope?: string[];
}) {
  const path = (step.scope || []).map((part) =>
    part.replace(
      /\[(\d+)\]$/,
      (_, index: string) => ` · item ${Number(index) + 1}`,
    ),
  );
  return [...path, step.definition_node_id || step.node_id].join(" / ");
}
const terminal = new Set(["completed", "failed", "cancelled"]);
const tone = (state: string) =>
  state === "completed"
    ? "green"
    : state === "failed"
      ? "amber"
      : state === "skipped" || state === "cancelled"
        ? "neutral"
        : "purple";

export function WorkflowConsole({
  workspaceId,
  initial,
  initialSelected,
  canRun,
  canReview,
  userId,
}: {
  workspaceId: string;
  initial: WorkflowExecution[];
  initialSelected?: string;
  canRun: boolean;
  canReview: boolean;
  userId: string;
}) {
  const router = useRouter();
  const base = `/workspaces/${workspaceId}/workflow-runs`;
  const [runs, setRuns] = useState(initial);
  const [selectedId, setSelectedId] = useState(
    initialSelected || initial[0]?.id || "",
  );
  const [detail, setDetail] = useState<WorkflowExecution | null>(null);
  const [step, setStep] = useState<StepDetail | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [confirmed, setConfirmed] = useState(false);
  const pendingReplay = useRef<{ source: string; key: string } | null>(null);
  const selected =
    detail?.id === selectedId
      ? detail
      : runs.find((run) => run.id === selectedId);
  const selectedState = selected?.state;
  const hasActive = runs.some((run) => !terminal.has(run.state));
  useEffect(() => {
    if (!selectedId) return;
    let active = true;
    async function update() {
      try {
        const next = await api<WorkflowExecution>(`${base}/${selectedId}`);
        if (active) setDetail(next);
      } catch (cause) {
        if (active)
          setError(
            cause instanceof Error ? cause.message : "Could not read this run.",
          );
      }
    }
    void update();
    const timer =
      !selectedState || !terminal.has(selectedState)
        ? window.setInterval(update, 3000)
        : null;
    return () => {
      active = false;
      if (timer !== null) window.clearInterval(timer);
    };
  }, [base, selectedId, selectedState]);
  useEffect(() => {
    if (!hasActive) return;
    const timer = window.setInterval(() => {
      api<{ items: WorkflowExecution[] }>(base)
        .then((result) => setRuns(result.items))
        .catch(() => {});
    }, 3000);
    return () => window.clearInterval(timer);
  }, [base, hasActive]);
  async function refresh() {
    setBusy(true);
    setError("");
    try {
      setRuns((await api<{ items: WorkflowExecution[] }>(base)).items);
      if (selectedId)
        setDetail(await api<WorkflowExecution>(`${base}/${selectedId}`));
    } catch (cause) {
      setError(
        cause instanceof Error
          ? cause.message
          : "Could not refresh workflow history.",
      );
    } finally {
      setBusy(false);
    }
  }
  async function inspect(nodeId: string) {
    setBusy(true);
    setError("");
    try {
      setStep(await api<StepDetail>(`${base}/${selectedId}/steps/${nodeId}`));
    } catch (cause) {
      setError(
        cause instanceof Error
          ? cause.message
          : "Step evidence is unavailable for this older run.",
      );
    } finally {
      setBusy(false);
    }
  }
  async function cancel() {
    setBusy(true);
    setError("");
    try {
      const next = await api<WorkflowExecution>(
        `${base}/${selectedId}/cancel`,
        { method: "POST" },
      );
      setDetail(next);
      setRuns((current) =>
        current.map((run) => (run.id === next.id ? next : run)),
      );
    } catch (cause) {
      setError(
        cause instanceof Error ? cause.message : "Could not cancel run.",
      );
    } finally {
      setBusy(false);
    }
  }
  async function replay() {
    setBusy(true);
    setError("");
    if (pendingReplay.current?.source !== selectedId)
      pendingReplay.current = { source: selectedId, key: crypto.randomUUID() };
    try {
      const next = await api<WorkflowExecution>(
        `${base}/${selectedId}/replay`,
        {
          method: "POST",
          headers: { "Idempotency-Key": pendingReplay.current.key },
          body: JSON.stringify({ confirm_external: confirmed }),
        },
      );
      setRuns((current) => [
        next,
        ...current.filter((run) => run.id !== next.id),
      ]);
      setDetail(next);
      setSelectedId(next.id);
      router.replace(
        `/w/${workspaceId}/executions?kind=workflows&runId=${next.id}`,
        { scroll: false },
      );
      setStep(null);
      setConfirmed(false);
      pendingReplay.current = null;
    } catch (cause) {
      setError(
        cause instanceof Error
          ? cause.message
          : "Replay was not confirmed. Retrying this request reuses its event key.",
      );
    } finally {
      setBusy(false);
    }
  }
  async function decide(pauseId: string, decision: "approve" | "reject") {
    setBusy(true);
    setError("");
    try {
      const next = await api<WorkflowExecution>(
        `${base}/${selectedId}/approvals/${pauseId}/decision`,
        { method: "POST", body: JSON.stringify({ decision }) },
      );
      setDetail(next);
      setRuns((current) =>
        current.map((run) => (run.id === next.id ? next : run)),
      );
      setStep(null);
    } catch (cause) {
      setError(
        cause instanceof Error
          ? cause.message
          : "This decision could not be saved.",
      );
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <PageHeader
        eyebrow="WORKFLOW OPERATIONS"
        title="Workflow executions"
        description="Inspect durable progress, failure evidence, resource use and safe recovery."
        action={
          <Button variant="outline" disabled={busy} onClick={refresh}>
            <RefreshCw size={15} />
            Refresh
          </Button>
        }
      />
      {error && <ErrorNotice message={error} />}
      <div className="run-layout">
        <section className="run-history">
          <div className="run-panel-heading">
            <h2>Recent workflows</h2>
            <span>Last 50</span>
          </div>
          {runs.length ? (
            runs.map((run) => (
              <button
                key={run.id}
                disabled={busy}
                className={`run-list-row ${run.id === selectedId ? "active" : ""}`}
                onClick={() => {
                  setSelectedId(run.id);
                  setStep(null);
                  setConfirmed(false);
                  setError("");
                }}
              >
                <span>
                  <strong>{run.id.slice(0, 8)}</strong>
                  <small>
                    <LocalTime value={run.created_at} />
                    {run.automation_id
                      ? " · Automation"
                      : run.deployment_id
                        ? " · Deployment"
                        : ""}
                  </small>
                </span>
                <Badge tone={tone(run.state)}>{run.state}</Badge>
              </button>
            ))
          ) : (
            <EmptyState
              icon={<Clock3 size={25} />}
              title="No workflow runs yet"
            >
              Publish and run a workflow, or connect it to a trigger.{" "}
              <Link href={`/w/${workspaceId}/workflows`}>Open workflows</Link>
            </EmptyState>
          )}
        </section>
        <section className="run-detail">
          {selected ? (
            <>
              <div className="run-panel-heading">
                <div>
                  <span className="eyebrow">Published workflow run</span>
                  <h2>{selected.id.slice(0, 8)}</h2>
                </div>
                <Badge tone={tone(selected.state)}>{selected.state}</Badge>
              </div>
              <dl className="run-facts">
                <div>
                  <dt>Version</dt>
                  <dd>{selected.version_id.slice(0, 8)}</dd>
                </div>
                <div>
                  <dt>Reserved model budget</dt>
                  <dd>${Number(selected.reserved_max_usd).toFixed(4)}</dd>
                </div>
                <div>
                  <dt>Measured cost</dt>
                  <dd>
                    {selected.cost_usd === null
                      ? "—"
                      : `$${Number(selected.cost_usd).toFixed(8)}`}
                  </dd>
                </div>
                <div>
                  <dt>Recorded tokens</dt>
                  <dd>
                    {selected.input_tokens ?? "—"} in /{" "}
                    {selected.output_tokens ?? "—"} out
                  </dd>
                </div>
              </dl>
              {selected.uncertain_cost_usd && (
                <div className="run-warning">
                  A provider outcome is uncertain. Up to $
                  {selected.uncertain_cost_usd} may be charged in addition to
                  any recorded measured cost.
                </div>
              )}
              {selected.error_code && (
                <ErrorNotice
                  message={`Run ended: ${selected.error_code.replaceAll("_", " ").toLowerCase()}. Inspect the failed step and its input before replaying.`}
                />
              )}
              {selected.output !== null && (
                <div className="run-output">
                  <h3>Validated output</h3>
                  <pre>{JSON.stringify(selected.output, null, 2)}</pre>
                </div>
              )}
              {!!selected.pauses?.length && (
                <section className="workflow-pause-panel">
                  <h3>Decisions and timers</h3>
                  {selected.pauses.map((pause) => (
                    <div className="workflow-pause-card" key={pause.id}>
                      <div className="row between">
                        <strong>
                          {pause.kind === "approval"
                            ? "Human approval"
                            : "Wait timer"}{" "}
                          · {pause.node_id}
                        </strong>
                        <Badge
                          tone={tone(
                            pause.state === "approved" ||
                              pause.state === "elapsed"
                              ? "completed"
                              : pause.state,
                          )}
                        >
                          {pause.state}
                        </Badge>
                      </div>
                      {pause.prompt && <p>{pause.prompt}</p>}
                      <p>
                        {pause.kind === "approval"
                          ? "Decision deadline"
                          : "Resume after"}
                        : <LocalTime value={pause.due_at} />
                      </p>
                      {pause.state === "pending" && (
                        <>
                          <Button
                            size="sm"
                            variant="outline"
                            disabled={busy}
                            onClick={() => inspect(pause.node_id)}
                          >
                            Inspect saved input
                          </Button>
                          {step?.node_id === pause.node_id && (
                            <div className="approval-input-evidence">
                              <h4>Saved input for this decision</h4>
                              <pre>{JSON.stringify(step.input, null, 2)}</pre>
                            </div>
                          )}
                          {pause.kind === "approval" &&
                            (canReview &&
                            (pause.allow_requester ||
                              userId !== selected.requested_by) ? (
                              <>
                                <p>
                                  Inspect the saved input before deciding.
                                  Approval continues this published version with
                                  the same data. Rejection ends the run.
                                </p>
                                <Button
                                  size="sm"
                                  disabled={
                                    busy || step?.node_id !== pause.node_id
                                  }
                                  onClick={() => decide(pause.id, "approve")}
                                >
                                  Approve and continue
                                </Button>{" "}
                                <Button
                                  size="sm"
                                  variant="outline"
                                  disabled={
                                    busy || step?.node_id !== pause.node_id
                                  }
                                  onClick={() => decide(pause.id, "reject")}
                                >
                                  Reject run
                                </Button>
                              </>
                            ) : (
                              <p>
                                {!canReview
                                  ? "A workspace owner or admin must review this request."
                                  : "Another owner or admin must review this run."}
                              </p>
                            ))}
                          <p>
                            The worker is released while waiting. The run slot
                            and model budget reservation remain held.
                          </p>
                        </>
                      )}
                      {pause.decided_by && (
                        <p>
                          Reviewer: {pause.decided_by.slice(0, 8)}
                          {pause.settled_at && (
                            <>
                              {" "}
                              · <LocalTime value={pause.settled_at} />
                            </>
                          )}
                        </p>
                      )}
                    </div>
                  ))}
                </section>
              )}
              <div className="run-trace">
                <h3>Durable step trace</h3>
                {selected.steps?.length ? (
                  <ol>
                    {selected.steps.map((item, index) => (
                      <li key={item.node_id}>
                        <span>{index + 1}</span>
                        <div
                          style={{
                            paddingInlineStart: Math.min(
                              (item.scope?.length || 0) * 12,
                              36,
                            ),
                          }}
                        >
                          <button
                            className="text-link"
                            disabled={busy}
                            onClick={() => inspect(item.node_id)}
                          >
                            {stepLabel(item)} · {item.type.replaceAll("_", " ")}
                          </button>
                          <small>
                            {item.status} · attempt {item.attempt}
                            {item.duration_ms !== null
                              ? ` · ${item.duration_ms} ms`
                              : ""}
                            {item.selected_port
                              ? ` · ${selectedPathLabel(item.selected_port)}`
                              : ""}
                            {item.error_code ? ` · ${item.error_code}` : ""}
                          </small>
                        </div>
                        <Badge tone={tone(item.status)}>{item.status}</Badge>
                      </li>
                    ))}
                  </ol>
                ) : (
                  <p>
                    {detail?.id !== selectedId
                      ? "Loading step evidence…"
                      : terminal.has(selected.state)
                        ? "Step records are unavailable for this older run."
                        : "Waiting for the worker to checkpoint its first step."}
                  </p>
                )}
              </div>
              {step &&
                !selected.pauses?.some(
                  (pause) =>
                    pause.state === "pending" && pause.node_id === step.node_id,
                ) && (
                  <section className="workflow-step-evidence">
                    <div className="row between">
                      <h3>{stepLabel(step)} evidence</h3>
                      <Badge tone={tone(step.status)}>{step.status}</Badge>
                      <Button
                        variant="outline"
                        size="sm"
                        disabled={busy}
                        onClick={() => inspect(step.node_id)}
                      >
                        Refresh evidence
                      </Button>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => setStep(null)}
                      >
                        Close
                      </Button>
                    </div>
                    <p>
                      Input and output are encrypted in storage and visible to
                      workspace members.
                    </p>
                    {step.iteration_index !== null &&
                      step.iteration_index !== undefined && (
                        <p>
                          Loop item {step.iteration_index + 1}. Its receipt is
                          retained independently of later items.
                        </p>
                      )}
                    <h4>Input JSON</h4>
                    <pre>{JSON.stringify(step.input, null, 2)}</pre>
                    <h4>Output JSON</h4>
                    <pre>{JSON.stringify(step.output, null, 2)}</pre>
                    {step.error_code && (
                      <p className="field-error">{step.error_code}</p>
                    )}
                    {step.usage && (
                      <p>Recorded model usage: {JSON.stringify(step.usage)}</p>
                    )}
                  </section>
                )}
              {canRun &&
                (!terminal.has(selected.state) ? (
                  <Button
                    variant="outline"
                    disabled={busy || selected.cancel_requested}
                    onClick={cancel}
                  >
                    <Square size={14} />
                    {selected.cancel_requested
                      ? "Cancellation requested"
                      : "Cancel run"}
                  </Button>
                ) : (
                  <section className="workflow-replay">
                    <label>
                      <input
                        type="checkbox"
                        checked={confirmed}
                        onChange={(e) => setConfirmed(e.target.checked)}
                      />
                      Start a new run with the same version and input. External
                      steps may repeat requests and provider charges.
                    </label>
                    <Button
                      variant="outline"
                      disabled={busy || !confirmed}
                      onClick={replay}
                    >
                      <RotateCcw size={14} />
                      Replay as new run
                    </Button>
                  </section>
                ))}
            </>
          ) : (
            <EmptyState
              icon={<Clock3 size={25} />}
              title="Select a workflow run"
            >
              Its status, step evidence and resource use appear here.
            </EmptyState>
          )}
        </section>
      </div>
    </>
  );
}
