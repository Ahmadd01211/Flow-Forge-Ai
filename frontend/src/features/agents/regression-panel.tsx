"use client";
import { useEffect, useState } from "react";
import { api } from "@/lib/api/client";
import { Button } from "@/components/ui/button";
import { Badge, ErrorNotice } from "@/components/shared/ui";
import type { components } from "@/lib/api/generated";

type Suite = components["schemas"]["SuitePublic"];
type Result = components["schemas"]["EvaluationResult"];

export function RegressionPanel({
  workspaceId,
  agentId,
  versionId,
  canEdit,
}: {
  workspaceId: string;
  agentId: string;
  versionId: string;
  canEdit: boolean;
}) {
  const base = `/workspaces/${workspaceId}/agents/${agentId}/evaluations`;
  const [suites, setSuites] = useState<Suite[]>([]);
  const [suiteId, setSuiteId] = useState("");
  const [name, setName] = useState("");
  const [cases, setCases] = useState(
    '[{"name":"Outage ticket","input":{"ticket":"The service is down"},"expected_output":{"priority":"urgent"}}]',
  );
  const [result, setResult] = useState<Result | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => {
    let active = true;
    api<{ items: Suite[] }>(base)
      .then((r) => {
        if (active) {
          setSuites(r.items);
          setSuiteId(r.items[0]?.id || "");
        }
      })
      .catch((e) => {
        if (active)
          setError(
            e instanceof Error
              ? e.message
              : "Could not load regression suites.",
          );
      });
    return () => {
      active = false;
    };
  }, [base]);
  async function create() {
    setBusy(true);
    setError("");
    try {
      const row = await api<Suite>(base, {
        method: "POST",
        body: JSON.stringify({ name, cases: JSON.parse(cases) }),
      });
      setSuites([row, ...suites]);
      setSuiteId(row.id);
      setResult(null);
      setName("");
    } catch (cause) {
      setError(
        cause instanceof Error ? cause.message : "Could not save examples.",
      );
    } finally {
      setBusy(false);
    }
  }
  async function evaluate() {
    setBusy(true);
    setError("");
    setResult(null);
    try {
      setResult(
        await api<Result>(`${base}/${suiteId}/evaluate`, {
          method: "POST",
          body: JSON.stringify({ version_id: versionId }),
        }),
      );
    } catch (cause) {
      setError(
        cause instanceof Error ? cause.message : "Could not evaluate examples.",
      );
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="regression-panel">
      <h3>Regression examples</h3>
      <p>
        Compare expected JSON with this version&apos;s latest matching completed
        runs (up to 100 recent runs). No model calls are made. Missing evidence
        is untested.
      </p>
      {error && <ErrorNotice message={error} />}
      {suites.length ? (
        <div className="form-stack">
          <label>
            Saved example suite
            <select
              value={suiteId}
              disabled={busy}
              onChange={(e) => {
                setSuiteId(e.target.value);
                setResult(null);
              }}
            >
              {suites.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name}
                </option>
              ))}
            </select>
          </label>
          <Button
            variant="outline"
            disabled={busy || !suiteId}
            onClick={evaluate}
          >
            {busy ? "Please wait…" : "Evaluate observed runs"}
          </Button>
        </div>
      ) : (
        <p>No saved regression examples yet.</p>
      )}
      {result && (
        <div role="status">
          <p>
            {result.passed} of {result.total} examples have matching observed
            output.
          </p>
          {result.items.map((r, i) => (
            <div className="row between" key={i}>
              <span>{r.name}</span>
              <Badge tone={r.status === "passed" ? "green" : "amber"}>
                {r.status.replaceAll("_", " ")}
              </Badge>
              {r.run_id && <small>Run {r.run_id.slice(0, 8)}</small>}
            </div>
          ))}
        </div>
      )}
      {canEdit && (
        <details>
          <summary>Save a new example suite</summary>
          <div className="form-stack">
            <label>
              Suite name
              <input
                maxLength={100}
                value={name}
                onChange={(e) => setName(e.target.value)}
              />
            </label>
            <label>
              Examples JSON
              <textarea
                className="json-editor"
                rows={8}
                maxLength={65536}
                value={cases}
                onChange={(e) => setCases(e.target.value)}
              />
            </label>
            <p>
              Up to 20 examples. Inputs and expected outputs are encrypted in
              storage. Make ordinary agent runs separately before scoring their
              output here.
            </p>
            <Button disabled={busy || !name.trim()} onClick={create}>
              Save examples
            </Button>
          </div>
        </details>
      )}
    </section>
  );
}
