"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Activity, ArrowRight, Clock3, LoaderCircle, Play, Square } from "lucide-react";
import { Badge, EmptyState, ErrorNotice, PageHeader } from "@/components/shared/ui";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api/client";
import type { AgentRun, AgentVersion, RunEvent, RunList } from "@/lib/api/types";

const terminal = new Set(["completed", "failed", "cancelled"]);
const stateTone = (state: string) =>
  state === "completed" ? "green" : state === "failed" ? "amber" : "purple";

export function RunConsole({
  workspaceId,
  initialRuns,
  version,
  canRun,
}: {
  workspaceId: string;
  initialRuns: AgentRun[];
  version: AgentVersion | null;
  canRun: boolean;
}) {
  const [runs, setRuns] = useState(initialRuns);
  const [selectedId, setSelectedId] = useState(initialRuns[0]?.id || "");
  const [input, setInput] = useState("{}");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [events, setEvents] = useState<RunEvent[]>([]);
  const base = `/workspaces/${workspaceId}/runs`;
  const selected = runs.find((run) => run.id === selectedId);
  const selectedState = selected?.state;
  const hasActive = runs.some((run) => !terminal.has(run.state));

  useEffect(() => {
    if (!hasActive) return;
    const timer = window.setInterval(async () => {
      try {
        const result = await api<RunList>(base);
        setRuns(result.items);
      } catch {
        // The next refresh can recover from a transient network interruption.
      }
    }, 3000);
    return () => window.clearInterval(timer);
  }, [base, hasActive]);

  useEffect(() => {
    if (!selectedId) return;
    let live = true;
    async function refreshTrace() {
      try {
        const result = await api<{ items: RunEvent[] }>(`${base}/${selectedId}/events`);
        if (live) setEvents(result.items);
      } catch {
        if (live) setEvents([]);
      }
    }
    void refreshTrace();
    const timer = selectedState && !terminal.has(selectedState) ? window.setInterval(refreshTrace, 3000) : null;
    return () => { live = false; if (timer) window.clearInterval(timer); };
  }, [base, selectedId, selectedState]);

  async function submit() {
    setError("");
    if (!version) return;
    let payload: unknown;
    try {
      payload = JSON.parse(input);
      if (!payload || Array.isArray(payload) || typeof payload !== "object")
        throw new Error("Input must be a JSON object.");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Enter valid JSON input.");
      return;
    }
    setBusy(true);
    try {
      const run = await api<AgentRun>(base, {
        method: "POST",
        headers: { "Idempotency-Key": crypto.randomUUID() },
        body: JSON.stringify({ version_id: version.id, input: payload }),
      });
      setRuns((old) => [run, ...old.filter((item) => item.id !== run.id)]);
      setSelectedId(run.id);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Unable to start the run.");
    } finally {
      setBusy(false);
    }
  }

  async function cancel() {
    if (!selected) return;
    setBusy(true);
    setError("");
    try {
      const run = await api<AgentRun>(`${base}/${selected.id}/cancel`, { method: "POST" });
      setRuns((old) => old.map((item) => (item.id === run.id ? run : item)));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Unable to cancel the run.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="page-content">
      <PageHeader
        eyebrow="Agent execution"
        title="Runs"
        description="Run a published agent, then inspect its outcome, usage, and cost."
        action={<Badge tone="purple"><Activity size={12} /> Live history</Badge>}
      />
      {error && <ErrorNotice message={error} />}
      {version && (
        <section className="run-submit">
          <div className="row between">
            <div>
              <div className="eyebrow">Published snapshot v{version.number}</div>
              <h2>{version.name}</h2>
              <p>{version.config.provider} · {version.config.model_id} · up to ${version.config.limits.max_cost_usd} per run</p>
            </div>
            <Badge tone="green">Ready to run</Badge>
          </div>
          <label htmlFor="run-input">Input JSON</label>
          <textarea
            id="run-input"
            className="run-input"
            spellCheck={false}
            value={input}
            onChange={(event) => setInput(event.target.value)}
            disabled={!canRun || busy}
          />
          <div className="run-submit-footer">
            <span>A live run uses your connected provider key and may incur charges.</span>
            <Button onClick={submit} disabled={!canRun || busy}>
              {busy ? <LoaderCircle size={15} className="spin" /> : <Play size={15} />}
              Run published agent
            </Button>
          </div>
        </section>
      )}
      <div className="run-layout">
        <section className="run-history">
          <div className="run-panel-heading"><h2>Recent runs</h2><span>Last 50</span></div>
          {!runs.length ? (
            <EmptyState icon={<Clock3 size={25} />} title="No runs yet">
              Publish an agent and start a run to see its history here.
            </EmptyState>
          ) : runs.map((run) => (
            <button
              key={run.id}
              className={`run-list-row ${run.id === selectedId ? "active" : ""}`}
              onClick={() => setSelectedId(run.id)}
            >
              <span><strong>{run.id.slice(0, 8)}</strong><small>{new Date(run.created_at).toLocaleString()}</small></span>
              <Badge tone={stateTone(run.state)}>{run.state}</Badge>
            </button>
          ))}
        </section>
        <section className="run-detail">
          {selected ? (
            <>
              <div className="run-panel-heading">
                <div><span className="eyebrow">Run detail</span><h2>{selected.id.slice(0, 8)}</h2></div>
                <Badge tone={stateTone(selected.state)}>{selected.state}</Badge>
              </div>
              <dl className="run-facts">
                <div><dt>Started</dt><dd>{selected.started_at ? new Date(selected.started_at).toLocaleString() : "Waiting for worker"}</dd></div>
                <div><dt>Maximum estimated cost</dt><dd>${selected.reserved_max_usd}</dd></div>
                <div><dt>Measured cost</dt><dd>{selected.cost_usd ? `$${selected.cost_usd}` : "—"}</dd></div>
                <div><dt>Tokens</dt><dd>{selected.input_tokens ?? "—"} in / {selected.output_tokens ?? "—"} out</dd></div>
              </dl>
              {selected.uncertain_cost_usd && (
                <div className="run-warning">The provider request may have completed, but its outcome could not be confirmed. Up to ${selected.uncertain_cost_usd} may have been charged.</div>
              )}
              {selected.error_code && <ErrorNotice message={`Run ended: ${selected.error_code.replaceAll("_", " ").toLowerCase()}.`} />}
              {selected.output && (
                <div className="run-output"><div className="run-panel-heading"><h3>Output</h3><Badge tone="green">Validated JSON</Badge></div><pre>{JSON.stringify(selected.output, null, 2)}</pre></div>
              )}
              <div className="run-trace"><h3>Execution trace</h3>{events.length ? <ol>{events.map((event) => <li key={event.id}><span>{event.sequence}</span><div><strong>{event.kind === "tool" ? event.tool_key : event.kind}</strong><small>{event.status}{event.input_tokens !== null ? ` · ${event.input_tokens} in / ${event.output_tokens} out` : ""}{event.error_code ? ` · ${event.error_code}` : ""}</small></div><time>{new Date(event.created_at).toLocaleTimeString()}</time></li>)}</ol> : <p>No trace events yet.</p>}</div>
              {!terminal.has(selected.state) && canRun && (
                <Button variant="outline" size="sm" onClick={cancel} disabled={busy || selected.cancel_requested}>
                  <Square size={13} /> {selected.cancel_requested ? "Cancellation requested" : "Cancel run"}
                </Button>
              )}
              <div className="run-detail-footer">
                <Link href={`/w/${workspaceId}/agents`} className="text-link">Agents library <ArrowRight size={13} /></Link>
                <code>{selected.id}</code>
              </div>
            </>
          ) : (
            <EmptyState icon={<Activity size={25} />} title="Select a run">
              Run details and output appear here.
            </EmptyState>
          )}
        </section>
      </div>
    </div>
  );
}
