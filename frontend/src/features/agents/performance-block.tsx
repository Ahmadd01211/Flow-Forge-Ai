"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { LoaderCircle } from "lucide-react";
import { LocalTime } from "@/components/shared/local-time";
import { api } from "@/lib/api/client";
import { barHeights } from "@/features/workspace/overview-model";
import { usd, type Performance } from "@/features/executions/trace-model";

/** Run health for one agent: volume, success, speed, cost, tools, errors and feedback. */
export function PerformanceBlock({ workspaceId, agentId }: { workspaceId: string; agentId: string }) {
  const [days, setDays] = useState(7);
  const [tests, setTests] = useState(false);
  const [data, setData] = useState<Performance | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    let cancelled = false;
    api<Performance>(`/workspaces/${workspaceId}/agents/${agentId}/performance?days=${days}&include_tests=${tests}`)
      .then((result) => { if (!cancelled) { setData(result); setError(""); } })
      .catch((cause) => { if (!cancelled) setError(cause instanceof Error ? cause.message : "Could not load performance."); });
    return () => { cancelled = true; };
  }, [workspaceId, agentId, days, tests]);

  const runs = (id: string) => `/w/${workspaceId}/executions/${id}`;
  const heights = data ? barHeights(data.daily.map((day) => day.runs)) : [];
  const topCalls = Math.max(1, ...(data?.tools.map((tool) => tool.calls) ?? [1]));
  return (
    <div className="perf">
      <div className="builder-row">
        <div className="segmented perf-range" role="radiogroup" aria-label="Time range">
          {[7, 30].map((value) => (
            <button key={value} type="button" role="radio" aria-checked={days === value} className={days === value ? "active" : ""} onClick={() => setDays(value)}>{value} days</button>
          ))}
        </div>
        <label className="checkbox-row perf-tests">
          <input type="checkbox" checked={tests} onChange={(event) => setTests(event.target.checked)} /> Include test chats
        </label>
      </div>
      {error && <p className="builder-hint warn">{error}</p>}
      {!data ? (
        <p className="builder-hint"><LoaderCircle size={13} className="spin" /> Loading…</p>
      ) : !data.runs ? (
        <p className="builder-hint">No runs in the last {days} days{tests ? "" : " (test chats excluded)"}. Publish and chat with the agent, or call it from a workflow or deployment.</p>
      ) : (
        <>
          <div className="perf-tiles">
            <div><span>Runs</span><strong>{data.runs}</strong><small>{data.failed} failed</small></div>
            <div><span>Success</span><strong>{data.success_rate === null ? "—" : `${Math.round(data.success_rate * 100)}%`}</strong><small>of finished runs</small></div>
            <div><span>Avg cost</span><strong>{usd(data.cost_avg_usd)}</strong><small>{usd(data.cost_total_usd, Number(data.cost_total_usd) < 1 ? 4 : 2)} total</small></div>
            <div><span>Speed</span><strong>{data.duration_p50_s ?? "—"}s</strong><small>median · p95 {data.duration_p95_s ?? "—"}s</small></div>
            <div><span>Feedback</span><strong>👍 {data.feedback.up} · 👎 {data.feedback.down}</strong><small>{data.tokens_avg ? `~${data.tokens_avg.toLocaleString()} tokens/run` : ""}</small></div>
          </div>
          <div className="perf-chart" role="img" aria-label={`Runs per day: ${data.daily.map((day) => `${day.date} ${day.runs}`).join(", ")}`}>
            {data.daily.map((day, index) => (
              <span key={day.date} className="perf-bar" title={`${day.date}: ${day.runs} runs${day.failed ? `, ${day.failed} failed` : ""}`}>
                <span style={{ height: `${heights[index]}%` }} className={day.failed ? "has-failed" : ""} />
              </span>
            ))}
          </div>
          {data.tools.length > 0 && (
            <div className="perf-section">
              <strong>Most-used tools and skills</strong>
              {data.tools.map((tool) => (
                <div key={tool.tool_key} className="perf-tool">
                  <span>{tool.kind === "skill" ? "📘" : "🔧"} {tool.label}</span>
                  <span className="perf-tool-bar"><span style={{ width: `${(tool.calls / topCalls) * 100}%` }} /></span>
                  <small>{tool.calls}{tool.failed ? ` · ${tool.failed} failed` : ""}</small>
                </div>
              ))}
            </div>
          )}
          {data.errors.length > 0 && (
            <div className="perf-section">
              <strong>Most common errors</strong>
              <div className="builder-chips">{data.errors.map((item) => <span key={item.code} className="library-chip"><code>{item.code}</code> × {item.count}</span>)}</div>
            </div>
          )}
          {data.feedback.recent_down.length > 0 && (
            <div className="perf-section">
              <strong>Recent 👎</strong>
              {data.feedback.recent_down.map((item) => (
                <Link key={item.run_id} href={runs(item.run_id)} className="perf-link">“{item.comment || "No comment"}” · <LocalTime value={item.created_at} /></Link>
              ))}
            </div>
          )}
          <div className="perf-section">
            <strong>Recent runs</strong>
            {data.recent.map((run) => (
              <Link key={run.id} href={runs(run.id)} className="perf-link">
                <i className={`dot ${run.state}`} /> {run.state} · <LocalTime value={run.created_at} /> · {run.duration_s ?? "—"}s · {usd(run.cost_usd)}{run.source !== "manual" ? ` · ${run.source}` : ""}{run.error_code ? ` · ${run.error_code}` : ""}
              </Link>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
