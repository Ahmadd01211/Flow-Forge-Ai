"use client";
import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  AlertTriangle,
  ArrowRight,
  Bot,
  CalendarClock,
  Check,
  ChevronDown,
  CircleAlert,
  Clock3,
  Globe2,
  LoaderCircle,
  MessageSquare,
  PauseCircle,
  PlugZap,
  X,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge, ChecklistItem, ErrorNotice } from "@/components/shared/ui";
import { LocalTime } from "@/components/shared/local-time";
import { api } from "@/lib/api/client";
import {
  SOURCE_LABELS,
  activityLabel,
  attentionItems,
  barHeights,
  duration,
  editHref,
  money,
  percent,
  runHref,
  setupSteps,
  type OverviewData,
} from "./overview-model";

const STATE_TONE = { completed: "green", failed: "amber", cancelled: "neutral", waiting: "purple", running: "purple", queued: "neutral" } as const;

export function SetupChecklist({ data, base }: { data: OverviewData; base: string }) {
  const steps = setupSteps(data.setup, base);
  const required = steps.filter((step) => !step.optional);
  return (
    <section className="panel overview-setup">
      <div className="panel-header">
        <div>
          <h2>Get your workspace running</h2>
          <p>Each step ticks itself off as you complete it. The dashboard opens when the first four are done.</p>
        </div>
        <Badge tone={data.setup.complete ? "green" : "neutral"}>
          {required.filter((step) => step.done).length}/{required.length} done
        </Badge>
      </div>
      {steps.map((step) => (
        <ChecklistItem
          key={step.key}
          done={step.done}
          title={step.title}
          description={step.description}
          action={
            step.done ? <Badge tone="green">Done</Badge> : (
              <Link className="text-link" href={step.href}>
                {step.action} <ArrowRight size={14} />
              </Link>
            )
          }
        />
      ))}
    </section>
  );
}

function ApprovalCard({ approval, workspaceId, canDecide }: { approval: OverviewData["attention"]["approvals"][number]; workspaceId: string; canDecide: boolean }) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [input, setInput] = useState<unknown>(undefined);
  const [busy, setBusy] = useState<"" | "approve" | "reject" | "load">("");
  const [error, setError] = useState("");
  const runs = `/workspaces/${workspaceId}/workflow-runs/${approval.run_id}`;
  async function toggle() {
    setOpen(!open);
    if (open || input !== undefined) return;
    setBusy("load");
    try {
      const step = await api<{ input?: unknown }>(`${runs}/steps/${encodeURIComponent(approval.node_id)}`);
      setInput(step.input ?? null);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not load the step input.");
    } finally {
      setBusy("");
    }
  }
  async function decide(decision: "approve" | "reject") {
    setBusy(decision);
    setError("");
    try {
      await api(`${runs}/approvals/${approval.pause_id}/decision`, { method: "POST", body: JSON.stringify({ decision }) });
      router.refresh();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "The decision was not recorded.");
      setBusy("");
    }
  }
  const blockedForYou = approval.requested_by_you && !approval.allow_requester;
  return (
    <div className="overview-approval">
      <button type="button" className="overview-approval-summary" aria-expanded={open} onClick={toggle}>
        <PauseCircle size={16} />
        <span>
          <strong>{approval.workflow_name} v{approval.version_number}</strong>
          <small>{approval.step_label} · {approval.prompt || "Approval requested"} · expires <LocalTime value={approval.due_at} /></small>
        </span>
        <ChevronDown size={15} className={open ? "rotated" : ""} />
      </button>
      {open && (
        <div className="overview-approval-body">
          {busy === "load" ? (
            <LoaderCircle size={14} className="spin" aria-label="Loading the step input" />
          ) : input !== undefined ? (
            <>
              <span className="overview-label">Data waiting for approval</span>
              <pre>{JSON.stringify(input, null, 2)}</pre>
            </>
          ) : null}
          {canDecide ? (
            blockedForYou ? (
              <p className="overview-note">You started this run, and this step needs someone else to approve it.</p>
            ) : (
              <div className="row">
                <Button size="sm" onClick={() => decide("approve")} disabled={!!busy}>
                  {busy === "approve" ? <LoaderCircle size={14} className="spin" /> : <Check size={14} />}
                  Approve
                </Button>
                <Button size="sm" variant="outline" onClick={() => decide("reject")} disabled={!!busy}>
                  {busy === "reject" ? <LoaderCircle size={14} className="spin" /> : <X size={14} />}
                  Reject
                </Button>
              </div>
            )
          ) : (
            <p className="overview-note">Waiting for an owner or admin to decide.</p>
          )}
          {error && <ErrorNotice message={error} />}
        </div>
      )}
    </div>
  );
}

export function Attention({ data, base, workspaceId }: { data: OverviewData; base: string; workspaceId: string }) {
  const items = attentionItems(data, base);
  const { approvals, approvals_total: total } = data.attention;
  if (!items.length && !total) return null;
  return (
    <section className="panel overview-attention" aria-label="Needs attention">
      <div className="panel-header">
        <div>
          <h2>Needs attention</h2>
          <p>Decisions waiting on you and anything that will stop work from running.</p>
        </div>
        <Badge tone="amber">{items.length + total}</Badge>
      </div>
      {approvals.map((approval) => (
        <ApprovalCard key={approval.pause_id} approval={approval} workspaceId={workspaceId} canDecide={data.can_decide} />
      ))}
      {total > approvals.length && (
        <Link className="text-link" href={`${base}/executions?kind=workflows`}>
          {total - approvals.length} more waiting <ArrowRight size={14} />
        </Link>
      )}
      {items.map((item) => (
        <div className={`overview-alert ${item.tone}`} key={item.key}>
          {item.tone === "critical" ? <CircleAlert size={15} /> : <AlertTriangle size={15} />}
          <span>{item.text}</span>
          <Link className="text-link" href={item.href}>
            {item.action} <ArrowRight size={13} />
          </Link>
        </div>
      ))}
    </section>
  );
}

function Tiles({ data, base }: { data: OverviewData; base: string }) {
  const { usage } = data;
  const finished = usage.completed_today + usage.failed_today;
  const tiles = [
    { label: "Runs today", value: `${usage.accepted_runs}`, note: `of ${usage.daily_run_limit} allowed per day` },
    { label: "Active now", value: `${usage.active_runs}`, note: `of ${usage.active_run_limit} at a time` },
    {
      label: "Spend today",
      value: money(usage.committed_usd),
      note: `of ${money(usage.daily_budget_usd)} · ${money(usage.measured_usd)} recorded${Number(usage.uncertain_usd) ? `, ${money(usage.uncertain_usd)} possible` : ""}${Number(usage.reserved_usd) ? `, ${money(usage.reserved_usd)} reserved` : ""}`,
    },
    { label: "Success rate", value: finished ? percent(usage.completed_today / finished) : "—", note: finished ? `${usage.completed_today} of ${finished} finished runs today` : "No runs finished today" },
    { label: "Tokens today", value: (usage.input_tokens + usage.output_tokens).toLocaleString(), note: `${usage.input_tokens.toLocaleString()} in · ${usage.output_tokens.toLocaleString()} out` },
  ];
  return (
    <div className="overview-tiles">
      {tiles.map((tile) => (
        <article className="metric-card" key={tile.label}>
          <div className="metric-label">{tile.label}</div>
          <strong>{tile.value}</strong>
          <p>{tile.note}</p>
        </article>
      ))}
      <Link className="overview-tiles-link text-link" href={`${base}/usage`}>
        Limits reset <LocalTime value={usage.resets_at} format="time" /> · Usage details <ArrowRight size={13} />
      </Link>
    </div>
  );
}

function TrendChart({ title, trend, value, format, empty }: { title: string; trend: OverviewData["trend"]; value: (day: OverviewData["trend"][number]) => number; format: (day: OverviewData["trend"][number]) => string; empty: string }) {
  const heights = barHeights(trend.map(value));
  const blank = heights.every((height) => height === 0);
  const weekday = (date: string) => new Date(`${date}T00:00:00Z`).toLocaleDateString(undefined, { weekday: "short", timeZone: "UTC" });
  return (
    <figure className="overview-trend">
      <figcaption>{title}</figcaption>
      {blank && <p className="overview-trend-empty">{empty}</p>}
      <div className="overview-bars" role="img" aria-label={`${title}: ${trend.map((day) => `${weekday(day.date)} ${format(day)}`).join(", ")}`}>
        {trend.map((day, index) => (
          <button type="button" className="overview-bar-slot" key={day.date} aria-label={`${weekday(day.date)}: ${format(day)}`}>
            <span className="overview-bar" style={{ height: `${heights[index]}%` }} />
            <span className="overview-bar-tip" role="tooltip">
              <strong>{new Date(`${day.date}T00:00:00Z`).toLocaleDateString(undefined, { month: "short", day: "numeric", timeZone: "UTC" })}</strong>
              {format(day)}
            </span>
            <span className="overview-bar-day">{weekday(day.date)}</span>
          </button>
        ))}
      </div>
    </figure>
  );
}

function Trends({ data }: { data: OverviewData }) {
  return (
    <section className="panel overview-trends">
      <div className="panel-header">
        <div>
          <h2>Last 7 days</h2>
          <p>Agent and workflow runs per day (UTC), and their recorded model spend.</p>
        </div>
      </div>
      <div className="overview-trend-grid">
        <TrendChart title="Runs" trend={data.trend} value={(day) => day.runs} format={(day) => `${day.runs} run${day.runs === 1 ? "" : "s"}${day.failed ? `, ${day.failed} failed` : ""}`} empty="No runs in the last 7 days" />
        <TrendChart title="Spend" trend={data.trend} value={(day) => Number(day.cost_usd)} format={(day) => money(day.cost_usd)} empty="No model spend recorded in the last 7 days" />
      </div>
      <details className="overview-table-view">
        <summary>Show as table</summary>
        <table>
          <thead><tr><th>Day (UTC)</th><th>Runs</th><th>Failed</th><th>Spend</th></tr></thead>
          <tbody>
            {data.trend.map((day) => (
              <tr key={day.date}><td>{day.date}</td><td>{day.runs}</td><td>{day.failed}</td><td>{money(day.cost_usd)}</td></tr>
            ))}
          </tbody>
        </table>
      </details>
    </section>
  );
}

function RecentRuns({ data, base }: { data: OverviewData; base: string }) {
  return (
    <section className="panel">
      <div className="panel-header">
        <div><h2>Recent runs</h2><p>The latest agent and workflow runs.</p></div>
        <Link className="text-link" href={`${base}/executions`}>All runs <ArrowRight size={13} /></Link>
      </div>
      {data.recent_runs.length ? (
        <ul className="overview-list">
          {data.recent_runs.map((run) => (
            <li key={`${run.kind}-${run.id}`}>
              <Link href={runHref(run, base)}>
                <span className="overview-list-main">
                  <strong>{run.name} <small>v{run.version_number}</small></strong>
                  <small>
                    {SOURCE_LABELS[run.source]} · <LocalTime value={run.created_at} /> · {duration(run.duration_seconds)}
                    {run.cost_usd ? ` · ${money(run.cost_usd)}` : ""}
                    {run.error_code ? ` · ${run.error_code}` : ""}
                  </small>
                </span>
                <Badge tone={STATE_TONE[run.state]}>{run.state}</Badge>
              </Link>
            </li>
          ))}
        </ul>
      ) : (
        <p className="overview-empty">No runs yet. Publish a workflow and run it to see it here.</p>
      )}
    </section>
  );
}

function RecentEdits({ data, base }: { data: OverviewData; base: string }) {
  const label = { draft: "Never published", published: "Published", changed: "Unpublished changes" } as const;
  const tone = { draft: "neutral", published: "green", changed: "amber" } as const;
  return (
    <section className="panel">
      <div className="panel-header">
        <div><h2>Recently edited</h2><p>Workflows and agents, with publish status.</p></div>
      </div>
      {data.recent_edits.length ? (
        <ul className="overview-list">
          {data.recent_edits.map((edit) => (
            <li key={`${edit.kind}-${edit.id}`}>
              <Link href={editHref(edit, base)}>
                <span className="overview-list-main">
                  <strong>{edit.name}</strong>
                  <small>{edit.kind === "workflow" ? "Workflow" : "Agent"} · edited <LocalTime value={edit.updated_at} />{edit.version_number ? ` · latest v${edit.version_number}` : ""}</small>
                </span>
                <Badge tone={tone[edit.status]}>{label[edit.status]}</Badge>
              </Link>
            </li>
          ))}
        </ul>
      ) : (
        <p className="overview-empty">Nothing built yet.</p>
      )}
    </section>
  );
}

function Triggers({ data, base }: { data: OverviewData; base: string }) {
  const { schedules, webhooks, chat, deployments } = data.triggers;
  const empty = !schedules.length && !webhooks.length && !chat.length && !deployments;
  return (
    <section className="panel">
      <div className="panel-header">
        <div><h2>Upcoming & live triggers</h2><p>What starts your work without you.</p></div>
        <Link className="text-link" href={`${base}/automations`}>Manage <ArrowRight size={13} /></Link>
      </div>
      {empty ? (
        <p className="overview-empty">No schedules, webhooks, chat triggers or deployments yet.</p>
      ) : (
        <ul className="overview-list compact">
          {schedules.map((row) => (
            <li key={row.id}>
              <CalendarClock size={15} />
              <span className="overview-list-main">
                <strong>{row.name}</strong>
                <small>{row.next_due_at ? <>Next <LocalTime value={row.next_due_at} /></> : "Not scheduled"}{row.cron_expression ? ` · ${row.cron_expression}` : row.interval_seconds ? ` · every ${duration(row.interval_seconds)}` : ""}</small>
              </span>
              {row.last_error_code && <Badge tone="amber">{row.last_error_code}</Badge>}
            </li>
          ))}
          {webhooks.map((row) => (
            <li key={row.id}>
              <PlugZap size={15} />
              <span className="overview-list-main"><strong>{row.name}</strong><small>Webhook</small></span>
              {row.last_error_code && <Badge tone="amber">{row.last_error_code}</Badge>}
            </li>
          ))}
          {chat.map((row) => (
            <li key={row.workflow_id}>
              <MessageSquare size={15} />
              <span className="overview-list-main"><strong>{row.name}</strong><small>Chat · v{row.version_number}</small></span>
              <Link className="text-link" href={`${base}/workflows/${row.workflow_id}/chat`}>Open chat</Link>
            </li>
          ))}
          {deployments > 0 && (
            <li>
              <Globe2 size={15} />
              <span className="overview-list-main"><strong>{deployments} active deployment{deployments === 1 ? "" : "s"}</strong><small>Callable with an API key</small></span>
              <Link className="text-link" href={`${base}/deployments`}>View</Link>
            </li>
          )}
        </ul>
      )}
    </section>
  );
}

function Activity({ data, base }: { data: OverviewData; base: string }) {
  if (!data.activity) return null;
  return (
    <section className="panel">
      <div className="panel-header">
        <div><h2>Recent activity</h2><p>Changes and decisions in this workspace.</p></div>
        <Link className="text-link" href={`${base}/settings/activity`}>Full log <ArrowRight size={13} /></Link>
      </div>
      {data.activity.length ? (
        <ul className="overview-list compact">
          {data.activity.map((event) => (
            <li key={event.id}>
              <Clock3 size={15} />
              <span className="overview-list-main">
                <strong>{event.actor_name} {activityLabel(event.action)}</strong>
                <small><LocalTime value={event.created_at} /></small>
              </span>
            </li>
          ))}
        </ul>
      ) : (
        <p className="overview-empty">No activity yet.</p>
      )}
    </section>
  );
}

export function OverviewDashboard({ data, base, workspaceId }: { data: OverviewData; base: string; workspaceId: string }) {
  return (
    <>
      <Attention data={data} base={base} workspaceId={workspaceId} />
      <Tiles data={data} base={base} />
      <Trends data={data} />
      <div className="dashboard-grid overview-grid">
        <RecentRuns data={data} base={base} />
        <RecentEdits data={data} base={base} />
        <Triggers data={data} base={base} />
        <Activity data={data} base={base} />
      </div>
      {!data.setup.complete ? null : (
        <p className="overview-footnote">
          <Bot size={13} /> {data.counts.agents} agent{data.counts.agents === 1 ? "" : "s"} · {data.counts.workflows} workflow{data.counts.workflows === 1 ? "" : "s"} ·{" "}
          <Link className="text-link" href={`${base}/overview?view=setup`}>Setup checklist</Link>
        </p>
      )}
    </>
  );
}
