"use client";
import { LocalTime } from "@/components/shared/local-time";

import { useState } from "react";
import { RefreshCw } from "lucide-react";
import { Badge, ErrorNotice, PageHeader } from "@/components/shared/ui";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api/client";
import type { components } from "@/lib/api/generated";

export type Usage = components["schemas"]["UsageRead"];
const money = (value: string) =>
  new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: 2,
    maximumFractionDigits: 6,
  }).format(Number(value));

export function UsagePanel({
  workspaceId,
  initial,
  canManage,
}: {
  workspaceId: string;
  initial: Usage;
  canManage: boolean;
}) {
  const base = `/workspaces/${workspaceId}/usage`;
  const [data, setData] = useState(initial);
  const [budget, setBudget] = useState(initial.daily_budget_usd);
  const [runLimit, setRunLimit] = useState(initial.daily_run_limit);
  const [activeLimit, setActiveLimit] = useState(initial.active_run_limit);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const percent =
    Number(data.daily_budget_usd) > 0
      ? Math.min(
          100,
          (100 * Number(data.committed_usd)) / Number(data.daily_budget_usd),
        )
      : 0;
  async function refresh() {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const next = await api<Usage>(base);
      setData(next);
      setBudget(next.daily_budget_usd);
      setRunLimit(next.daily_run_limit);
      setActiveLimit(next.active_run_limit);
    } catch (cause) {
      setError(
        cause instanceof Error ? cause.message : "Could not refresh usage.",
      );
    } finally {
      setBusy(false);
    }
  }
  async function save() {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      setData(
        await api<Usage>(base, {
          method: "PATCH",
          body: JSON.stringify({
            expected_revision: data.revision,
            daily_budget_usd: budget,
            daily_run_limit: runLimit,
            active_run_limit: activeLimit,
          }),
        }),
      );
      setNotice("Workspace limits saved. They apply to new runs immediately.");
    } catch (cause) {
      setError(
        cause instanceof Error ? cause.message : "Could not save limits.",
      );
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <PageHeader
        eyebrow="WORKSPACE CONTROLS"
        title="Usage & budgets"
        description="Track recorded usage and control new agent and workflow runs together."
        action={
          <Button variant="outline" disabled={busy} onClick={refresh}>
            <RefreshCw size={15} />
            Refresh
          </Button>
        }
      />
      {error && <ErrorNotice message={error} />}
      {notice && <p role="status">{notice}</p>}
      <div className="usage-summary">
        {[
          ["Measured cost", money(data.measured_usd)],
          ["Reserved for active runs", money(data.reserved_usd)],
          ["Possible uncertain charges", money(data.uncertain_usd)],
          ["Budget remaining", money(data.remaining_usd)],
        ].map(([label, value]) => (
          <section className="panel usage-stat" key={label}>
            <span>{label}</span>
            <strong>{value}</strong>
          </section>
        ))}
      </div>
      <section className="panel usage-details">
        <div className="row between">
          <h2>Daily admission window</h2>
          <Badge>{data.active_runs} active runs</Badge>
        </div>
        <p>
          {money(data.committed_usd)} committed against{" "}
          {money(data.daily_budget_usd)}. Resets{" "}
          <LocalTime value={data.resets_at} /> (midnight UTC).
        </p>
        <div
          className="usage-meter"
          role="progressbar"
          aria-label="Daily committed budget"
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={Math.round(percent)}
        >
          <span style={{ width: `${percent}%` }} />
        </div>
        <div className="policy-line">
          <span>Accepted today</span>
          <strong>
            {data.accepted_runs} / {data.daily_run_limit}
          </strong>
        </div>
        <div className="policy-line">
          <span>Shared active capacity</span>
          <strong>
            {data.active_runs} / {data.active_run_limit}
          </strong>
        </div>
        <div className="policy-line">
          <span>Recorded tokens</span>
          <strong>
            {data.input_tokens.toLocaleString()} input ·{" "}
            {data.output_tokens.toLocaleString()} output
          </strong>
        </div>
        <p>
          Totals use runs accepted today, plus reservations for any active runs
          carried over from an earlier day. Unknown provider outcomes retain a
          possible-charge estimate. Cancelled runs still count toward the daily
          run limit.
        </p>
        <p>
          Costs are estimates from reviewed token prices and provider usage,
          rather than an invoice guarantee. MCP service fees are outside these
          token estimates.
        </p>
      </section>
      <section className="panel usage-details">
        <h2>Workspace limits</h2>
        {canManage ? (
          <div className="form-stack">
            <label>
              Daily model budget (USD)
              <input
                inputMode="decimal"
                value={budget}
                maxLength={14}
                disabled={busy}
                onChange={(e) => setBudget(e.target.value)}
              />
            </label>
            <label>
              Daily accepted-run limit
              <input
                type="number"
                min={1}
                max={10000}
                step={1}
                value={runLimit}
                disabled={busy}
                onChange={(e) => setRunLimit(Number(e.target.value))}
              />
            </label>
            <label>
              Shared active-run limit
              <input
                type="number"
                min={1}
                max={4}
                step={1}
                value={activeLimit}
                disabled={busy}
                onChange={(e) => setActiveLimit(Number(e.target.value))}
              />
            </label>
            <p>
              A zero model budget blocks new paid model runs. Pure local
              workflows can still run within count and capacity limits. Each run
              type also has a maximum of two active runs. Lowering a limit
              blocks new admissions and leaves accepted runs intact.
            </p>
            <Button disabled={busy || !budget} onClick={save}>
              {busy ? "Please wait…" : "Save workspace limits"}
            </Button>
          </div>
        ) : (
          <p>A workspace owner or admin can change these limits.</p>
        )}
      </section>
    </>
  );
}
