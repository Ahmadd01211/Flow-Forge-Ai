"use client";
import { LocalTime } from "@/components/shared/local-time";

import { useState } from "react";
import Link from "next/link";
import {
  CalendarClock,
  Clock3,
  KeyRound,
  Pause,
  Play,
  RefreshCw,
  Webhook,
} from "lucide-react";
import {
  Badge,
  EmptyState,
  ErrorNotice,
  PageHeader,
} from "@/components/shared/ui";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api/client";
import type { components } from "@/lib/api/generated";

export type Automation = components["schemas"]["AutomationRead"];
export type EligibleTrigger = components["schemas"]["EligibleTrigger"];
type Run = {
  id: string;
  state: string;
  error_code: string | null;
  created_at: string;
};
type Secret = components["schemas"]["AutomationSecret"];
type SchedulePreview = components["schemas"]["SchedulePreview"];

const CRON_PRESETS = [
  ["Weekdays 09:00", "0 9 * * 1-5"],
  ["Daily 08:00", "0 8 * * *"],
  ["Mondays 09:00", "0 9 * * 1"],
  ["Every hour", "0 * * * *"],
] as const;

function timezones(): string[] {
  try {
    return Intl.supportedValuesOf("timeZone");
  } catch {
    return [];
  }
}

function zonedTime(value: string, timeZone: string): string {
  return new Intl.DateTimeFormat(undefined, {
    timeZone,
    weekday: "short",
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

export function cadenceLabel(row: Automation): string {
  if (row.kind !== "schedule") return "Authenticated webhook";
  return row.cron_expression
    ? `Cron ${row.cron_expression} · ${row.timezone}`
    : `Every ${row.interval_seconds} seconds`;
}

export function AutomationsPanel({
  workspaceId,
  initial,
  eligible,
  canManage,
}: {
  workspaceId: string;
  initial: Automation[];
  eligible: EligibleTrigger[];
  canManage: boolean;
}) {
  const base = `/workspaces/${workspaceId}/automations`;
  const [items, setItems] = useState(initial);
  const [version, setVersion] = useState(eligible[0]?.version_id || "");
  const [name, setName] = useState("");
  const [interval, setIntervalSeconds] = useState(300);
  const [cadence, setCadence] = useState<"interval" | "cron">("interval");
  const [cron, setCron] = useState("0 9 * * 1-5");
  const [timezone, setTimezone] = useState("");
  const [preview, setPreview] = useState<SchedulePreview | null>(null);
  const [input, setInput] = useState("{}");
  const [secret, setSecret] = useState<Secret | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [history, setHistory] = useState<{ id: string; items: Run[] } | null>(
    null,
  );
  const selected = eligible.find((v) => v.version_id === version);
  function replace(row: Automation) {
    setItems((current) =>
      current.map((item) => (item.id === row.id ? row : item)),
    );
  }
  async function create() {
    if (!selected) return;
    setBusy(true);
    setError("");
    setSecret(null);
    try {
      const row = await api<Secret>(base, {
        method: "POST",
        body: JSON.stringify({
          name: name.trim(),
          version_id: version,
          kind: selected.kind,
          ...(selected.kind === "schedule"
            ? {
                input: JSON.parse(input),
                ...(cadence === "cron"
                  ? { cron_expression: cron.trim(), timezone: timezone.trim() }
                  : { interval_seconds: interval }),
              }
            : {}),
        }),
      });
      setItems((current) => [row, ...current]);
      setName("");
      if (row.webhook_key) setSecret(row);
    } catch (cause) {
      setError(
        cause instanceof Error ? cause.message : "Could not create automation.",
      );
    } finally {
      setBusy(false);
    }
  }
  function chooseCadence(next: "interval" | "cron") {
    setCadence(next);
    // Resolved on interaction, not render, so server and browser markup agree.
    if (next === "cron" && !timezone)
      setTimezone(Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC");
  }
  async function checkSchedule() {
    setBusy(true);
    setError("");
    setPreview(null);
    try {
      const query = new URLSearchParams({
        cron_expression: cron.trim(),
        timezone: timezone.trim(),
      });
      setPreview(
        await api<SchedulePreview>(`${base}/schedule-preview?${query}`),
      );
    } catch (cause) {
      setError(
        cause instanceof Error ? cause.message : "Could not check schedule.",
      );
    } finally {
      setBusy(false);
    }
  }
  async function change(row: Automation) {
    setBusy(true);
    setError("");
    try {
      replace(
        await api<Automation>(`${base}/${row.id}`, {
          method: "PATCH",
          body: JSON.stringify({
            state: row.state === "active" ? "paused" : "active",
          }),
        }),
      );
    } catch (cause) {
      setError(
        cause instanceof Error ? cause.message : "Could not update automation.",
      );
    } finally {
      setBusy(false);
    }
  }
  async function rotate(row: Automation) {
    setBusy(true);
    setError("");
    setSecret(null);
    try {
      const next = await api<Secret>(`${base}/${row.id}/rotate`, {
        method: "POST",
      });
      replace(next);
      setSecret(next);
    } catch (cause) {
      setError(
        cause instanceof Error
          ? cause.message
          : "Could not rotate webhook key.",
      );
    } finally {
      setBusy(false);
    }
  }
  async function refresh() {
    setBusy(true);
    setError("");
    try {
      setItems((await api<{ items: Automation[] }>(base)).items);
    } catch (cause) {
      setError(
        cause instanceof Error
          ? cause.message
          : "Could not refresh automations.",
      );
    } finally {
      setBusy(false);
    }
  }
  async function archive(row: Automation) {
    setBusy(true);
    setError("");
    try {
      await api<void>(`${base}/${row.id}`, { method: "DELETE" });
      setItems((current) => current.filter((item) => item.id !== row.id));
      if (secret?.id === row.id) setSecret(null);
    } catch (cause) {
      setError(
        cause instanceof Error
          ? cause.message
          : "Could not archive automation.",
      );
    } finally {
      setBusy(false);
    }
  }
  async function runs(row: Automation) {
    setBusy(true);
    setError("");
    try {
      const result = await api<{ items: Run[] }>(`${base}/${row.id}/runs`);
      setHistory({ id: row.id, items: result.items });
    } catch (cause) {
      setError(
        cause instanceof Error ? cause.message : "Could not load deliveries.",
      );
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <PageHeader
        eyebrow="AUTOMATION"
        title="Triggers & schedules"
        description="Start a published workflow from an authenticated event, a persistent interval or a calendar schedule."
      />
      {error && <ErrorNotice message={error} />}
      {secret?.webhook_key && (
        <section className="panel deployment-secret" aria-live="polite">
          <div className="row between">
            <h2>Save your webhook key</h2>
            <Badge tone="amber">Shown once</Badge>
          </div>
          <p>
            Store this key on the sending server. Rotating it invalidates the
            previous key.
          </p>
          <code className="automation-secret">{secret.webhook_key}</code>
          <p>
            POST <code>/api/v1/webhooks/{secret.id}</code>
          </p>
          <p>
            Headers: <code>Authorization: Bearer YOUR_KEY</code> and{" "}
            <code>Idempotency-Key: UNIQUE_EVENT_ID</code> (8–128 characters, no
            spaces).
          </p>
          <p>
            The request body is your workflow&apos;s input JSON object. Poll{" "}
            <code>/api/v1/webhooks/{secret.id}/runs/RUN_ID</code> using the same
            bearer key.
          </p>
          <Button variant="outline" onClick={() => setSecret(null)}>
            I saved the key
          </Button>
        </section>
      )}
      {canManage && (
        <section className="panel automation-create">
          <h2>Create automation</h2>
          {eligible.length ? (
            <div className="form-stack">
              <label>
                Published workflow
                <select
                  value={version}
                  disabled={busy}
                  onChange={(e) => setVersion(e.target.value)}
                >
                  {eligible.map((v) => (
                    <option key={v.version_id} value={v.version_id}>
                      {v.name} · v{v.number} · {v.kind}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Automation name
                <input
                  value={name}
                  maxLength={100}
                  disabled={busy}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="New support tickets"
                />
              </label>
              {selected?.kind === "schedule" && (
                <>
                  <div
                    className="segmented"
                    role="radiogroup"
                    aria-label="Schedule type"
                  >
                    {(
                      [
                        ["interval", "Fixed interval"],
                        ["cron", "Calendar (cron)"],
                      ] as const
                    ).map(([option, title]) => (
                      <button
                        type="button"
                        role="radio"
                        aria-checked={cadence === option}
                        key={option}
                        className={cadence === option ? "active" : ""}
                        disabled={busy}
                        onClick={() => chooseCadence(option)}
                      >
                        {title}
                      </button>
                    ))}
                  </div>
                  {cadence === "interval" ? (
                    <label>
                      Run every (seconds)
                      <input
                        type="number"
                        min={60}
                        max={86400}
                        step={1}
                        value={interval}
                        disabled={busy}
                        onChange={(e) =>
                          setIntervalSeconds(Number(e.target.value))
                        }
                      />
                    </label>
                  ) : (
                    <>
                      <div className="row">
                        {CRON_PRESETS.map(([title, value]) => (
                          <button
                            type="button"
                            className="chip-button"
                            key={value}
                            disabled={busy}
                            onClick={() => {
                              setCron(value);
                              setPreview(null);
                            }}
                          >
                            {title}
                          </button>
                        ))}
                      </div>
                      <label>
                        Cron expression
                        <input
                          value={cron}
                          maxLength={100}
                          disabled={busy}
                          spellCheck={false}
                          onChange={(e) => {
                            setCron(e.target.value);
                            setPreview(null);
                          }}
                          placeholder="0 9 * * 1-5"
                          aria-describedby="cron-help"
                        />
                      </label>
                      <small id="cron-help">
                        Five fields: minute, hour, day of month, month, day of
                        week. Example: <code>30 8 * * mon-fri</code> runs at
                        08:30 on weekdays.
                      </small>
                      <label>
                        Timezone
                        <input
                          list="automation-timezones"
                          value={timezone}
                          maxLength={64}
                          disabled={busy}
                          spellCheck={false}
                          onChange={(e) => {
                            setTimezone(e.target.value);
                            setPreview(null);
                          }}
                        />
                        <datalist id="automation-timezones">
                          {timezones().map((zone) => (
                            <option key={zone} value={zone} />
                          ))}
                        </datalist>
                      </label>
                      <div>
                        <Button
                          variant="outline"
                          disabled={busy || !cron.trim() || !timezone.trim()}
                          onClick={checkSchedule}
                        >
                          <CalendarClock size={14} />
                          Show next runs
                        </Button>
                      </div>
                      {preview && (
                        <div aria-live="polite">
                          <h4>Next runs ({preview.timezone})</h4>
                          <ul>
                            {preview.occurrences.map((value) => (
                              <li key={value}>
                                <time dateTime={value}>
                                  {zonedTime(value, preview.timezone)}
                                </time>
                              </li>
                            ))}
                          </ul>
                        </div>
                      )}
                    </>
                  )}
                  <label>
                    Input JSON
                    <textarea
                      className="json-editor"
                      rows={6}
                      value={input}
                      maxLength={65536}
                      disabled={busy}
                      onChange={(e) => setInput(e.target.value)}
                    />
                  </label>
                  <p>
                    {cadence === "cron"
                      ? "First run happens at the next matching time. When clocks change for daylight saving, a skipped time runs right after the change and a repeated fixed time runs once."
                      : "First run starts after one interval."}{" "}
                    Saved input is encrypted. Agent steps can incur provider
                    charges on every run. Missed runs are coalesced into one run
                    after downtime.
                  </p>
                </>
              )}
              <Button
                disabled={busy || !name.trim() || !selected}
                onClick={create}
              >
                {busy ? "Please wait…" : "Create automation"}
              </Button>
            </div>
          ) : (
            <p>
              Publish a workflow with a Webhook or Schedule trigger node first.{" "}
              <Link href={`/w/${workspaceId}/workflows`} className="text-link">
                Open workflows
              </Link>
            </p>
          )}
        </section>
      )}
      <div className="row between">
        <h2>Workspace automations</h2>
        <Button variant="outline" disabled={busy} onClick={refresh}>
          <RefreshCw size={15} />
          Refresh status
        </Button>
      </div>
      <p>
        Pausing blocks future deliveries. Already accepted runs continue; cancel
        them from Executions.
      </p>
      {items.length ? (
        <div className="deployment-cards">
          {items.map((row) => (
            <article className="panel deployment-card" key={row.id}>
              <div className="row between">
                <div className="row">
                  {row.kind === "webhook" ? (
                    <Webhook size={20} />
                  ) : (
                    <Clock3 size={20} />
                  )}
                  <div>
                    <h3>{row.name}</h3>
                    <small>{cadenceLabel(row)}</small>
                  </div>
                </div>
                <Badge tone={row.state === "active" ? "green" : "amber"}>
                  {row.state}
                </Badge>
              </div>
              {row.next_due_at && (
                <p>
                  Next due: <LocalTime value={row.next_due_at} />
                  {row.next_attempt_at && <> · Retry after <LocalTime value={row.next_attempt_at} format="time" /></>}
                </p>
              )}
              {row.kind === "webhook" && (
                <code className="automation-secret">
                  /api/v1/webhooks/{row.id}
                </code>
              )}
              {row.last_error_code && (
                <ErrorNotice
                  message={`Dispatch needs attention: ${row.last_error_code.replaceAll("_", " ").toLowerCase()}. Check permissions, the published version, and connected credentials.`}
                />
              )}
              <div className="row deployment-card-actions">
                <Button
                  variant="outline"
                  disabled={busy}
                  onClick={() => runs(row)}
                >
                  Recent deliveries
                </Button>
                {canManage && (
                  <>
                    <Button
                      variant="outline"
                      disabled={busy}
                      onClick={() => change(row)}
                    >
                      {row.state === "active" ? (
                        <Pause size={14} />
                      ) : (
                        <Play size={14} />
                      )}
                      {row.state === "active" ? "Pause" : "Resume"}
                    </Button>
                    <Button
                      variant="ghost"
                      disabled={busy}
                      onClick={() => archive(row)}
                    >
                      Archive
                    </Button>
                    {row.kind === "webhook" && (
                      <Button
                        variant="outline"
                        disabled={busy}
                        onClick={() => rotate(row)}
                      >
                        <KeyRound size={14} />
                        Rotate key
                      </Button>
                    )}
                  </>
                )}
              </div>
              {history?.id === row.id && (
                <div className="deployment-history">
                  <h4>Latest accepted runs</h4>
                  {history.items.length ? (
                    history.items.map((run) => (
                      <div className="row between" key={run.id}>
                      <Link className="text-link" href={`/w/${workspaceId}/executions?kind=workflows&runId=${run.id}`}>{run.id.slice(0, 8)}</Link>
                        <Badge
                          tone={run.state === "completed" ? "green" : "neutral"}
                        >
                          {run.state}
                        </Badge>
                        <small>
                          <LocalTime value={run.created_at} />
                          {run.error_code && ` · ${run.error_code}`}
                        </small>
                      </div>
                    ))
                  ) : (
                    <p>No deliveries accepted yet.</p>
                  )}
                </div>
              )}
            </article>
          ))}
        </div>
      ) : (
        <EmptyState icon={<Clock3 size={26} />} title="No automations yet">
          Connect a published workflow to an incoming event or a schedule.
        </EmptyState>
      )}
    </>
  );
}
