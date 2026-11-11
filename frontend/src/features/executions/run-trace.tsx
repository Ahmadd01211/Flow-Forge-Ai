"use client";
import { useState } from "react";
import Link from "next/link";
import { ArrowLeft, ChevronDown, Star } from "lucide-react";
import { Badge } from "@/components/shared/ui";
import { LocalTime } from "@/components/shared/local-time";
import { api } from "@/lib/api/client";
import { FeedbackButtons } from "./feedback";
import { STEP_ICON, ms, usd, waterfall, type TraceData } from "./trace-model";

const STATE_TONE = { completed: "green", failed: "amber", cancelled: "neutral", running: "purple", queued: "neutral" } as const;
const pretty = (value: unknown) => JSON.stringify(value, null, 2);

export function RunTrace({ workspaceId, trace, canEdit }: { workspaceId: string; trace: TraceData; canEdit: boolean }) {
  const { run, agent, steps, totals } = trace;
  const bars = waterfall(steps, run.started_at, run.finished_at);
  const [open, setOpen] = useState<number | null>(steps.findIndex((step) => step.status === "failed"));
  const [saved, setSaved] = useState("");
  const back = agent.workflow_id ? `/w/${workspaceId}/workflows/${agent.workflow_id}/edit` : `/w/${workspaceId}/agents/${agent.id}`;

  async function saveExample() {
    try {
      await api(`/workspaces/${workspaceId}/agents/${agent.id}/examples`, { method: "POST", body: JSON.stringify({ input: trace.input, expected_output: run.output }) });
      setSaved("Saved as a test example.");
    } catch (cause) {
      setSaved(cause instanceof Error ? cause.message : "Could not save the example.");
    }
  }

  return (
    <div className="run-trace-page">
      <header className="trace-head">
        <Link href={back} className="icon-button" aria-label="Back to the agent"><ArrowLeft size={18} /></Link>
        <div>
          <span className="row">
            <strong>{agent.name} · v{agent.version_number}</strong>
            <Badge tone={STATE_TONE[run.state as keyof typeof STATE_TONE] ?? "neutral"}>{run.state}</Badge>
            {agent.playground && <Badge tone="purple">Playground test</Badge>}
          </span>
          <small className="muted">
            {agent.provider}/{agent.model_id} · <LocalTime value={run.created_at} />
            {agent.skills.length > 0 && ` · skills: ${agent.skills.map((skill) => `${skill.name}${skill.number ? ` v${skill.number}` : ""}`).join(", ")}`}
          </small>
        </div>
        <div className="trace-actions">
          <FeedbackButtons workspaceId={workspaceId} runId={run.id} initial={trace.feedback.mine} />
          {canEdit && run.state === "completed" && !agent.workflow_id && (
            <button type="button" className="text-link" onClick={saveExample}><Star size={13} /> Save as example</button>
          )}
        </div>
      </header>
      {saved && <p className="builder-hint">{saved}</p>}
      <div className="trace-stats">
        <div><span>Duration</span><strong>{ms(totals.duration_ms)}</strong></div>
        <div><span>Cost</span><strong>{usd(run.cost_usd)}</strong>{run.uncertain_cost_usd && <small>up to {usd(run.uncertain_cost_usd)} uncertain</small>}</div>
        <div><span>Tokens</span><strong>{run.input_tokens ?? "—"} / {run.output_tokens ?? "—"}</strong><small>in / out</small></div>
        <div><span>Steps</span><strong>{totals.model_calls} 🧠 · {totals.tool_calls} 🔧</strong><small>model calls · tool and skill calls</small></div>
      </div>
      {run.error_code && <p className="trace-error">This run {run.state} with <code>{run.error_code}</code>.</p>}
      <div className="trace-grid">
        <section className="panel trace-timeline" aria-label="Timeline">
          <h2>What happened</h2>
          {!steps.length && <p className="muted">No steps were recorded for this run.</p>}
          <ol>
            {steps.map((step, index) => (
              <li key={index} className={`trace-step ${step.status} ${open === index ? "open" : ""}`}>
                <button type="button" className="trace-step-head" aria-expanded={open === index} onClick={() => setOpen(open === index ? null : index)}>
                  <span className="trace-icon" aria-hidden="true">{STEP_ICON[step.kind]}</span>
                  <span className="trace-step-label">
                    <strong>{step.kind === "skill" ? `Loaded skill · ${step.label}` : step.kind === "tool" ? step.label : `Model call ${steps.slice(0, index + 1).filter((item) => item.kind === "model").length}`}</strong>
                    <small>
                      {ms(step.duration_ms)}
                      {step.input_tokens !== null && ` · ${step.input_tokens} in / ${step.output_tokens ?? 0} out`}
                      {step.cost_usd && ` · ${usd(step.cost_usd)}`}
                      {step.error_code && ` · ${step.error_code}`}
                    </small>
                  </span>
                  <span className="trace-bar" aria-hidden="true"><span style={{ left: `${bars[index].left}%`, width: `${bars[index].width}%` }} /></span>
                  {step.kind !== "model" && <ChevronDown size={14} className={open === index ? "rotated" : ""} />}
                </button>
                {open === index && step.kind !== "model" && (
                  <div className="trace-step-body">
                    <span className="overview-label">Arguments</span>
                    <pre>{pretty(step.arguments)}</pre>
                    <span className="overview-label">{step.status === "failed" ? "Error" : "Result"}</span>
                    <pre>{step.output === null || step.output === undefined ? step.error_code ?? "—" : pretty(step.output)}</pre>
                  </div>
                )}
              </li>
            ))}
          </ol>
        </section>
        <aside className="trace-io">
          <section className="panel"><h2>Input</h2><pre>{pretty(trace.input)}</pre></section>
          <section className="panel"><h2>Output</h2><pre>{run.output ? pretty(run.output) : "—"}</pre></section>
          {trace.feedback.comments.length > 0 && (
            <section className="panel">
              <h2>Feedback</h2>
              <ul className="trace-comments">
                {trace.feedback.comments.map((item, index) => (
                  <li key={index}>{item.rating === "up" ? "👍" : "👎"} <strong>{item.author}</strong>: {item.comment} <small><LocalTime value={item.created_at} /></small></li>
                ))}
              </ul>
            </section>
          )}
        </aside>
      </div>
    </div>
  );
}
