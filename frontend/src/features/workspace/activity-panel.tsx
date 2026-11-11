"use client";

import Link from "next/link";
import { useState } from "react";
import { Download, RefreshCw, ShieldCheck } from "lucide-react";
import {
  Badge,
  EmptyState,
  ErrorNotice,
  PageHeader,
} from "@/components/shared/ui";
import { LocalTime } from "@/components/shared/local-time";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api/client";
import type { components } from "@/lib/api/generated";

type ActivityPage = components["schemas"]["ActivityPage"];

export function ActivityPanel({
  workspaceId,
  initial,
}: {
  workspaceId: string;
  initial: ActivityPage;
}) {
  const [page, setPage] = useState(initial),
    [action, setAction] = useState(""),
    [applied, setApplied] = useState("");
  const [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  const base = `/workspaces/${workspaceId}/activity`;
  async function load(cursor?: string) {
    setBusy(true);
    setError("");
    const filter = cursor ? applied : action.trim();
    try {
      const query = new URLSearchParams();
      if (filter) query.set("action", filter);
      if (cursor) query.set("cursor", cursor);
      setPage(await api<ActivityPage>(`${base}?${query}`));
      setApplied(filter);
    } catch (cause) {
      setError(
        cause instanceof Error ? cause.message : "Could not load activity.",
      );
    } finally {
      setBusy(false);
    }
  }
  function download() {
    const body = {
      schema_version: 1,
      workspace_id: workspaceId,
      exported_at: new Date().toISOString(),
      action: applied || null,
      items: page.items,
      next_cursor: page.next_cursor,
    };
    const href = URL.createObjectURL(
      new Blob([JSON.stringify(body, null, 2)], { type: "application/json" }),
    );
    const link = document.createElement("a");
    link.href = href;
    link.download = `flowforge-activity-${new Date().toISOString().slice(0, 10)}.json`;
    link.click();
    window.setTimeout(() => URL.revokeObjectURL(href), 1000);
  }
  return (
    <>
      <PageHeader
        eyebrow="WORKSPACE GOVERNANCE"
        title="Activity log"
        description="Review permissions, publications, approvals and credential changes. Configuration payloads and credentials are excluded."
        action={
          <Button
            variant="outline"
            disabled={busy || !page.items.length}
            onClick={download}
          >
            <Download size={16} />
            Export this page
          </Button>
        }
      />
      <Link href={`/w/${workspaceId}/settings`}>Back to settings</Link>
      {error && <ErrorNotice message={error} />}
      <form
        className="panel activity-filter"
        onSubmit={(e) => {
          e.preventDefault();
          void load();
        }}
      >
        <label>
          Filter by exact action
          <input
            value={action}
            maxLength={100}
            placeholder="workflow_pause.approved"
            onChange={(e) => setAction(e.target.value)}
          />
        </label>
        <Button variant="outline" disabled={busy} type="submit">
          <RefreshCw size={15} />
          {busy ? "Loading…" : "Apply / refresh"}
        </Button>
      </form>
      <section className="panel activity-list" aria-label="Workspace activity">
        <div className="row between">
          <h2>Recorded actions</h2>
          <Badge>{page.items.length} on this page</Badge>
        </div>
        {page.items.length ? (
          page.items.map((event) => (
            <article className="activity-event" key={event.id}>
              <div className="row between">
                <strong>{event.action}</strong>
                <LocalTime value={event.created_at} />
              </div>
              <p>
                Actor {event.actor_id.slice(0, 8)} · Target{" "}
                {event.target_id.slice(0, 8)}
              </p>
              <details>
                <summary>Event details</summary>
                <pre>{JSON.stringify(event, null, 2)}</pre>
              </details>
            </article>
          ))
        ) : (
          <EmptyState
            icon={<ShieldCheck size={24} />}
            title="No matching activity"
          >
            Publish a version, change a workspace setting or review an approval
            to record an action.
          </EmptyState>
        )}
        {page.next_cursor && (
          <Button
            variant="outline"
            disabled={busy}
            onClick={() => load(page.next_cursor!)}
          >
            Older activity
          </Button>
        )}
      </section>
    </>
  );
}
