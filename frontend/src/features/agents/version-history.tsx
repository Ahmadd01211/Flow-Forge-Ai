"use client";
import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  Check,
  ChevronDown,
  Clock3,
  FlaskConical,
  History,
  LoaderCircle,
  Play,
  RotateCcw,
  ShieldCheck,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge, EmptyState, ErrorNotice } from "@/components/shared/ui";
import { api } from "@/lib/api/client";
import type {
  Agent,
  AgentVersion,
  VersionList,
  Connection,
} from "@/lib/api/types";
import { compareDefinitions, displayValue } from "./version-diff";
import { isRunnableModel } from "./runnable-models";

export function VersionHistory({
  agent,
  initial,
  dirty,
  canEdit = true,
  connections,
}: {
  agent: Agent;
  initial: VersionList;
  dirty: boolean;
  canEdit?: boolean;
  connections: Connection[];
}) {
  const router = useRouter(),
    [extra, setExtra] = useState<AgentVersion[]>([]),
    [cursor, setCursor] = useState(initial.next_cursor),
    [selectedId, setSelectedId] = useState(initial.items[0]?.id || ""),
    [view, setView] = useState("diff"),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [confirm, setConfirm] = useState(false);
  const versions = [...initial.items, ...extra],
    selected = versions.find((v) => v.id === selectedId),
    base = `/workspaces/${agent.workspace_id}/agents/${agent.id}`;
  async function more() {
    setBusy(true);
    setError("");
    try {
      const page = await api<VersionList>(
        `${base}/versions?cursor=${encodeURIComponent(cursor || "")}`,
      );
      setExtra((rows) => [...rows, ...page.items]);
      setCursor(page.next_cursor);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unable to load history.");
    } finally {
      setBusy(false);
    }
  }
  async function restore() {
    if (!selected) return;
    setBusy(true);
    setError("");
    try {
      await api(`${base}/restore`, {
        method: "POST",
        body: JSON.stringify({
          version_id: selected.id,
          expected_revision: agent.revision,
        }),
      });
      setConfirm(false);
      router.refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Restore failed.");
    } finally {
      setBusy(false);
    }
  }
  if (!versions.length)
    return (
      <EmptyState
        icon={<History size={27} />}
        title="Your version history starts with a snapshot"
      >
        Save your instructions and create a test snapshot. A snapshot freezes
        configuration; it does not call a model or publish an agent.
      </EmptyState>
    );
  const changes = selected ? compareDefinitions(selected, agent) : [];
  return (
    <div className="version-history">
      {error && <ErrorNotice message={error} />}
      <div className="version-intro">
        <div>
          <h2>Configuration you can trace</h2>
          <p>Immutable snapshots stay unchanged as your draft evolves.</p>
        </div>
        <Badge tone="purple">
          <ShieldCheck size={12} />
          Frozen configuration
        </Badge>
      </div>
      <div className="version-layout">
        <aside className="version-timeline" aria-label="Agent snapshots">
          {versions.map((v) => (
            <button
              className={
                v.id === selectedId ? "version-row active" : "version-row"
              }
              key={v.id}
              onClick={() => {
                setSelectedId(v.id);
                setConfirm(false);
              }}
            >
              <span className="version-dot">
                <History size={14} />
              </span>
              <div>
                <strong>
                  Snapshot v{v.number}
                  <Badge tone="purple">{v.purpose}</Badge>
                </strong>
                <span>From draft r{v.source_revision}</span>
                <small>{new Date(v.created_at).toLocaleString()}</small>
                <p>{v.change_summary || "No change summary"}</p>
              </div>
            </button>
          ))}
          {cursor && (
            <Button size="sm" variant="ghost" onClick={more} disabled={busy}>
              <ChevronDown size={14} />
              Load older snapshots
            </Button>
          )}
        </aside>
        {selected && (
          <section className="version-detail">
            <div className="row between">
              <div>
                <h3>{selected.name}</h3>
                <span className="muted">
                  v{selected.number} · source revision{" "}
                  {selected.source_revision}
                </span>
              </div>
              <Badge>Read-only</Badge>
            </div>
            <div className="version-hash">
              <ShieldCheck size={13} />
              <span>
                SHA-256{" "}
                <code title={selected.config_hash}>
                  {selected.config_hash.slice(0, 20)}…
                </code>
              </span>
              <button
                className="text-link"
                onClick={() =>
                  navigator.clipboard
                    .writeText(selected.config_hash)
                    .catch(() =>
                      setError(
                        "Clipboard unavailable. Select the hash in the configuration view.",
                      ),
                    )
                }
              >
                Copy hash
              </button>
            </div>
            <div className="version-subtabs">
              <button
                className={view === "diff" ? "active" : ""}
                onClick={() => setView("diff")}
              >
                Compare to saved draft{" "}
                {changes.length ? `(${changes.length})` : ""}
              </button>
              <button
                className={view === "config" ? "active" : ""}
                onClick={() => setView("config")}
              >
                Frozen configuration
              </button>
            </div>
            {view === "config" ? (
              <textarea
                className="version-json"
                readOnly
                rows={18}
                aria-label="Immutable snapshot configuration"
                value={JSON.stringify(
                  {
                    name: selected.name,
                    description: selected.description,
                    config: selected.config,
                    config_hash: selected.config_hash,
                  },
                  null,
                  2,
                )}
              />
            ) : changes.length ? (
              <div className="version-diff-list">
                {changes.map((change) => (
                  <div className="version-change" key={change.path}>
                    <code>{change.path}</code>
                    <div>
                      <span>SNAPSHOT v{selected.number}</span>
                      <pre>{displayValue(change.before)}</pre>
                    </div>
                    <div>
                      <span>SAVED DRAFT r{agent.revision}</span>
                      <pre>{displayValue(change.after)}</pre>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="version-no-change">
                <Check size={20} />
                <strong>Matches your saved draft</strong>
                <p>
                  {dirty
                    ? "You have unsaved edits. Save them to compare the latest configuration."
                    : "The saved draft has no differences from this snapshot."}
                </p>
              </div>
            )}
            <div className="version-actions">
              {selected.purpose === "published" &&
                isRunnableModel(
                  connections,
                  selected.config.provider,
                  selected.config.model_id,
                ) && (
                  <Button asChild size="sm">
                    <Link
                      href={`/w/${agent.workspace_id}/executions?agentId=${agent.id}&versionId=${selected.id}`}
                    >
                      <Play size={14} /> Run agent
                    </Link>
                  </Button>
                )}
              <Button asChild variant="outline" size="sm">
                <Link
                  href={`/w/${agent.workspace_id}/agents/${agent.id}/test?version=${selected.id}`}
                >
                  <FlaskConical size={14} />
                  Validate example data
                </Link>
              </Button>
              <Button
                size="sm"
                variant="outline"
                onClick={() => setConfirm(true)}
                disabled={dirty || busy || !canEdit}
                title={
                  dirty
                    ? "Save or discard unsaved edits before restoring."
                    : undefined
                }
              >
                <RotateCcw size={14} />
                Restore as draft
              </Button>
            </div>
            {confirm && (
              <div className="restore-confirm" role="alert">
                <h3>Restore snapshot v{selected.number}?</h3>
                <p>
                  This replaces the saved draft with the selected configuration
                  and creates a new draft revision. Snapshot history stays
                  unchanged.
                </p>
                <div className="row">
                  <Button size="sm" onClick={restore} disabled={busy}>
                    {busy ? (
                      <LoaderCircle size={14} className="spin" />
                    ) : (
                      <RotateCcw size={14} />
                    )}
                    Confirm restore
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => setConfirm(false)}
                  >
                    Cancel
                  </Button>
                </div>
              </div>
            )}
            <div className="version-provenance">
              <Clock3 size={13} />
              <span>
                Created by <code>{selected.created_by.slice(0, 8)}</code> · No
                model execution recorded
              </span>
            </div>
          </section>
        )}
      </div>
    </div>
  );
}
