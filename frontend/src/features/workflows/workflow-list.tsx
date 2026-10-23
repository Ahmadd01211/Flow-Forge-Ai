"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import {
  ArrowUpRight,
  GitBranch,
  LoaderCircle,
  Plus,
  Search,
  Workflow as WorkflowIcon,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Badge,
  EmptyState,
  ErrorNotice,
  PageHeader,
} from "@/components/shared/ui";
import { api } from "@/lib/api/client";
import type { Workflow } from "@/lib/api/types";
export function WorkflowList({
  items,
  workspaceId,
}: {
  items: Workflow[];
  workspaceId: string;
}) {
  const router = useRouter(),
    [q, setQ] = useState(""),
    [creating, setCreating] = useState(false),
    [name, setName] = useState(""),
    [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  async function create(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const result = await api<Workflow>(
        `/workspaces/${workspaceId}/workflows`,
        { method: "POST", body: JSON.stringify({ name }) },
      );
      router.push(`/w/${workspaceId}/workflows/${result.id}/edit`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unable to create workflow.");
      setBusy(false);
    }
  }
  const visible = items.filter((w) =>
    w.name.toLowerCase().includes(q.toLowerCase()),
  );
  return (
    <>
      <PageHeader
        eyebrow="CONNECT THE POSSIBILITIES"
        title="Your workflows"
        description="A clear canvas for the way your work happens."
        action={
          <div className="row">
            <Button asChild variant="outline"><Link href={`/w/${workspaceId}/templates`}>Use a starter</Link></Button>
            <Button onClick={() => setCreating(true)}><Plus size={17} />Create workflow</Button>
          </div>
        }
      />
      <div className="workflow-getting-started">
        <strong>How to build a workflow</strong>
        <span>1. Create a canvas</span><span>2. Select a step and add a node</span><span>3. Configure, save and validate</span>
        <small>Manual input, approved local tools and result steps can publish and run today. Agent and branch nodes are editable drafts while their runtime is being completed.</small>
      </div>
      {error && <ErrorNotice message={error} />}
      <div className="collection-toolbar">
        <div className="collection-tabs">
          <button className="active">
            All workflows <span>{items.length}</span>
          </button>
          <span className="muted">Drafts</span>
        </div>
        <div className="search-input">
          <Search size={17} />
          <input
            aria-label="Search workflows"
            placeholder="Search workflows…"
            value={q}
            onChange={(e) => setQ(e.target.value)}
          />
        </div>
      </div>
      {creating && (
        <form onSubmit={create} className="panel create-inline">
          <div>
            <h2>Give your workflow a name</h2>
            <p>Start with a manual input and a result. Add your own steps.</p>
          </div>
          <label>
            <span className="sr-only">Workflow name</span>
            <input
              required
              maxLength={100}
              placeholder="e.g. Support ticket triage"
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </label>
          <Button disabled={busy || !name.trim()} type="submit">
            {busy ? (
              <LoaderCircle size={15} className="spin" />
            ) : (
              <Plus size={15} />
            )}
            Create
          </Button>
          <Button
            variant="ghost"
            type="button"
            onClick={() => setCreating(false)}
          >
            Cancel
          </Button>
          <Link className="text-link" href={`/w/${workspaceId}/templates`}>Browse workflow starters</Link>
        </form>
      )}
      {!items.length && !creating ? (
        <EmptyState
          icon={<GitBranch size={30} />}
          title="Connect your first workflow"
          action={
            <Button onClick={() => setCreating(true)}>
              <Plus size={16} />
              Create your first workflow
            </Button>
          }
        >
          Start with a manual input, arrange your steps, and let server-side
          validation help you refine the graph.
        </EmptyState>
      ) : (
        <div className="workflow-grid">
          {visible.map((w) => (
            <Link
              key={w.id}
              className="workflow-card"
              href={`/w/${workspaceId}/workflows/${w.id}/edit`}
            >
              <div className="workflow-card-preview">
                <span>
                  <WorkflowIcon size={21} />
                </span>
                <i />
                <span>
                  <GitBranch size={23} />
                </span>
                <i />
                <span>
                  <ArrowUpRight size={21} />
                </span>
                <span className="workflow-preview-dots" />
              </div>
              <div className="workflow-card-content">
                <div className="row between">
                  <h2>{w.name}</h2>
                  <Badge>Draft</Badge>
                </div>
                <p>
                  {w.graph.nodes.length} nodes · {w.graph.edges.length}{" "}
                  connections
                </p>
                <div className="row between">
                  <span className="muted">Revision {w.revision}</span>
                  <span className="text-link">
                    Open builder <ArrowUpRight size={15} />
                  </span>
                </div>
              </div>
            </Link>
          ))}
        </div>
      )}
      <div className="collection-note">
        <GitBranch size={16} />
        <span>
          Drafts are editable. Publishing and execution will be enabled after
          the runtime is verified.
        </span>
      </div>
    </>
  );
}
