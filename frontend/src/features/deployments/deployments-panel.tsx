"use client";

import { useState } from "react";
import Link from "next/link";
import {
  Bot,
  Copy,
  ExternalLink,
  GitBranch,
  KeyRound,
  Plus,
  RotateCw,
  ShieldCheck,
  Trash2,
} from "lucide-react";
import {
  Badge,
  EmptyState,
  ErrorNotice,
  PageHeader,
} from "@/components/shared/ui";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api/client";

export interface DeploymentEntry {
  id: string;
  workspace_id: string;
  name: string;
  kind: "agent" | "workflow";
  version_id: string;
  key_prefix: string;
  state: "active" | "revoked";
  created_at: string;
  rotated_at: string | null;
  revoked_at: string | null;
}

export interface EligibleVersion {
  kind: "agent" | "workflow";
  version_id: string;
  name: string;
  number: number;
}

interface KeyResult extends DeploymentEntry {
  api_key: string;
}

interface RecentRun {
  id: string;
  state: string;
  error_code: string | null;
  created_at: string;
  finished_at: string | null;
}

export function DeploymentsPanel({
  workspaceId,
  initialDeployments,
  eligibleVersions,
}: {
  workspaceId: string;
  initialDeployments: DeploymentEntry[];
  eligibleVersions: EligibleVersion[];
}) {
  const [items, setItems] = useState(initialDeployments);
  const [selectedVersion, setSelectedVersion] = useState(
    eligibleVersions[0]?.version_id || "",
  );
  const [name, setName] = useState("");
  const [revealed, setRevealed] = useState<KeyResult | null>(null);
  const [copied, setCopied] = useState(false);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [openHistory, setOpenHistory] = useState<string | null>(null);
  const [runHistory, setRunHistory] = useState<Record<string, RecentRun[]>>({});
  const base = `/workspaces/${workspaceId}/deployments`;
  const selected = eligibleVersions.find(
    (version) => version.version_id === selectedVersion,
  );

  async function create() {
    if (!selected || !name.trim()) return;
    setBusy("create");
    setError("");
    setRevealed(null);
    try {
      const result = await api<KeyResult>(base, {
        method: "POST",
        body: JSON.stringify({
          name: name.trim(),
          kind: selected.kind,
          version_id: selected.version_id,
        }),
      });
      setItems((current) => [result, ...current]);
      setRevealed(result);
      setCopied(false);
      setName("");
    } catch (cause) {
      setError(
        cause instanceof Error ? cause.message : "Could not create deployment.",
      );
    } finally {
      setBusy("");
    }
  }

  async function rotate(item: DeploymentEntry) {
    setBusy(item.id);
    setError("");
    setRevealed(null);
    try {
      const result = await api<KeyResult>(`${base}/${item.id}/rotate`, {
        method: "POST",
      });
      setItems((current) =>
        current.map((entry) => (entry.id === item.id ? result : entry)),
      );
      setRevealed(result);
      setCopied(false);
    } catch (cause) {
      setError(
        cause instanceof Error ? cause.message : "Could not rotate key.",
      );
    } finally {
      setBusy("");
    }
  }

  async function revoke(item: DeploymentEntry) {
    if (
      !window.confirm(
        `Revoke ${item.name}? Its key will stop working and active runs will be cancelled.`,
      )
    )
      return;
    setBusy(item.id);
    setError("");
    setRevealed(null);
    try {
      const result = await api<DeploymentEntry>(`${base}/${item.id}/revoke`, {
        method: "POST",
      });
      setItems((current) =>
        current.map((entry) => (entry.id === item.id ? result : entry)),
      );
    } catch (cause) {
      setError(
        cause instanceof Error ? cause.message : "Could not revoke deployment.",
      );
    } finally {
      setBusy("");
    }
  }

  async function copyKey() {
    if (!revealed) return;
    try {
      await navigator.clipboard.writeText(revealed.api_key);
      setCopied(true);
    } catch {
      setError("Clipboard access failed. Select the key to copy it manually.");
    }
  }

  async function toggleHistory(item: DeploymentEntry) {
    if (openHistory === item.id) {
      setOpenHistory(null);
      return;
    }
    setBusy(item.id);
    setError("");
    try {
      const result = await api<{ items: RecentRun[] }>(
        `${base}/${item.id}/runs`,
      );
      setRunHistory((current) => ({ ...current, [item.id]: result.items }));
      setOpenHistory(item.id);
    } catch (cause) {
      setError(
        cause instanceof Error
          ? cause.message
          : "Could not load deployment runs.",
      );
    } finally {
      setBusy("");
    }
  }

  return (
    <>
      <PageHeader
        eyebrow="HOSTED ACCESS"
        title="Deployments"
        description="Give your application a stable API endpoint for one published agent or workflow version."
      />
      {error && <ErrorNotice message={error} />}
      <div className="deployments-layout">
        <section className="panel deployment-create">
          <div className="deployment-section-title">
            <span className="node-icon purple">
              <Plus size={18} />
            </span>
            <div>
              <h2>Create deployment</h2>
              <p>
                Choose a published version. A new key appears once after
                creation.
              </p>
            </div>
          </div>
          {eligibleVersions.length ? (
            <div className="deployment-form">
              <label htmlFor="deployment-version">Published version</label>
              <select
                id="deployment-version"
                value={selectedVersion}
                onChange={(event) => setSelectedVersion(event.target.value)}
              >
                {eligibleVersions.map((version) => (
                  <option key={version.version_id} value={version.version_id}>
                    {version.kind === "agent" ? "Agent" : "Workflow"} ·{" "}
                    {version.name} · v{version.number}
                  </option>
                ))}
              </select>
              <label htmlFor="deployment-name">Deployment name</label>
              <input
                id="deployment-name"
                maxLength={100}
                value={name}
                onChange={(event) => setName(event.target.value)}
                placeholder="Customer support API"
              />
              <Button onClick={create} disabled={!!busy || !name.trim()}>
                <KeyRound size={16} />
                Create key and endpoint
              </Button>
            </div>
          ) : (
            <div className="deployment-empty">
              <p>Publish an executable agent or a linear workflow first.</p>
              <div className="row">
                <Button asChild variant="outline" size="sm">
                  <Link href={`/w/${workspaceId}/agents`}>Open agents</Link>
                </Button>
                <Button asChild variant="outline" size="sm">
                  <Link href={`/w/${workspaceId}/workflows`}>
                    Open workflows
                  </Link>
                </Button>
              </div>
            </div>
          )}
        </section>
        <section className="panel deployment-guide">
          <div className="deployment-section-title">
            <span className="node-icon blue">
              <ShieldCheck size={18} />
            </span>
            <div>
              <h2>How access works</h2>
              <p>Each key is limited to a single immutable version.</p>
            </div>
          </div>
          <ol>
            <li>
              Publish a version that has its provider and tools configured.
            </li>
            <li>
              Create a deployment and copy its key to your server&apos;s secret
              store.
            </li>
            <li>
              Send an input object, then poll the returned run ID for a result.
            </li>
          </ol>
          <p>
            Requests are limited to 60 submissions per minute per deployment.
            Rotate a key to invalidate the old one.
          </p>
        </section>
      </div>
      {revealed && (
        <section className="panel deployment-secret" aria-live="polite">
          <div className="row between">
            <div>
              <h2>Copy your new API key</h2>
              <p>
                This key is shown once. Save it in your application&apos;s
                server-side secret store.
              </p>
            </div>
            <Badge tone="amber">One-time display</Badge>
          </div>
          <div className="deployment-key">
            <code>{revealed.api_key}</code>
            <Button variant="outline" size="sm" onClick={copyKey}>
              <Copy size={14} />
              {copied ? "Copied" : "Copy key"}
            </Button>
          </div>
          <p>
            Endpoint: <code>/api/v1/deployments/{revealed.id}/invoke</code>
          </p>
          <Button variant="ghost" size="sm" onClick={() => setRevealed(null)}>
            I saved the key
          </Button>
        </section>
      )}
      <section className="deployment-list">
        <div className="row between">
          <h2>Active endpoints</h2>
          <Badge>
            {items.filter((item) => item.state === "active").length} active
          </Badge>
        </div>
        {items.length ? (
          <div className="deployment-cards">
            {items.map((item) => (
              <article className="panel deployment-card" key={item.id}>
                <div className="row between">
                  <div className="row">
                    <span
                      className={`node-icon ${item.kind === "agent" ? "purple" : "blue"}`}
                    >
                      {item.kind === "agent" ? (
                        <Bot size={18} />
                      ) : (
                        <GitBranch size={18} />
                      )}
                    </span>
                    <div>
                      <h3>{item.name}</h3>
                      <small>
                        {item.kind === "agent" ? "Agent" : "Workflow"} ·{" "}
                        {item.key_prefix}••••
                      </small>
                    </div>
                  </div>
                  <Badge tone={item.state === "active" ? "green" : "amber"}>
                    {item.state}
                  </Badge>
                </div>
                <div className="deployment-endpoint">
                  <span>Invoke endpoint</span>
                  <code>/api/v1/deployments/{item.id}/invoke</code>
                </div>
                <div className="row deployment-card-actions">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => toggleHistory(item)}
                    disabled={!!busy}
                  >
                    {openHistory === item.id ? "Hide runs" : "Recent runs"}
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => rotate(item)}
                    disabled={!!busy || item.state !== "active"}
                  >
                    <RotateCw size={14} />
                    Rotate key
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => revoke(item)}
                    disabled={!!busy || item.state !== "active"}
                  >
                    <Trash2 size={14} />
                    Revoke
                  </Button>
                  <a
                    href="/api/docs"
                    target="_blank"
                    rel="noreferrer"
                    className="text-link"
                  >
                    API docs <ExternalLink size={13} />
                  </a>
                </div>
                {openHistory === item.id && (
                  <div className="deployment-history">
                    <h4>Latest runs</h4>
                    {runHistory[item.id]?.length ? (
                      <ul>
                        {runHistory[item.id].map((run) => (
                          <li key={run.id}>
                            <code>{run.id.slice(0, 8)}</code>
                            <Badge
                              tone={
                                run.state === "completed"
                                  ? "green"
                                  : run.state === "failed"
                                    ? "amber"
                                    : "neutral"
                              }
                            >
                              {run.state}
                            </Badge>
                            <span>
                              {new Date(run.created_at).toLocaleString()}
                            </span>
                            {run.error_code && <small>{run.error_code}</small>}
                          </li>
                        ))}
                      </ul>
                    ) : (
                      <p>No calls have reached this deployment yet.</p>
                    )}
                  </div>
                )}
              </article>
            ))}
          </div>
        ) : (
          <EmptyState icon={<KeyRound size={26} />} title="No deployments yet">
            Publish a version and create an endpoint to use it from another
            application.
          </EmptyState>
        )}
      </section>
    </>
  );
}
