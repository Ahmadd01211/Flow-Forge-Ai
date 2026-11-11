"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import {
  ArrowRight,
  Bot,
  GitBranch,
  LoaderCircle,
  Sparkles,
  Download,
  Upload,
} from "lucide-react";
import { Badge, ErrorNotice, PageHeader } from "@/components/shared/ui";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api/client";
import { templatePresentation } from "@/features/workspace/task-start-model";

export interface TemplateEntry {
  key: string;
  kind: "agent" | "workflow";
  name: string;
  description: string;
  category: string;
  template_version: number;
  visibility?: "private" | "workspace" | "public";
  owned?: boolean;
}

export function TemplateGallery({
  workspaceId,
  templates,
  canCreate,
  focus,
}: {
  workspaceId: string;
  templates: TemplateEntry[];
  canCreate: boolean;
  focus?: string;
}) {
  const router = useRouter();
  const [items, setItems] = useState(templates);
  const [preview, setPreview] = useState<{
    name: string;
    config?: { instructions?: string };
    graph?: { nodes: { id: string; label: string; type: string }[] };
    setup_steps?: string[];
    sample_input?: Record<string, unknown>;
  } | null>(null);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");

  async function exportTemplate(item: TemplateEntry) {
    setBusy(item.key);
    setError("");
    try {
      const data = await api(`/templates/${item.key}/export`);
      const url = URL.createObjectURL(
        new Blob([JSON.stringify(data, null, 2)], { type: "application/json" }),
      );
      const link = document.createElement("a");
      link.href = url;
      link.download = `flowforge-${item.key}.json`;
      link.click();
      URL.revokeObjectURL(url);
    } catch (cause) {
      setError(
        cause instanceof Error ? cause.message : "Could not export template.",
      );
    } finally {
      setBusy("");
    }
  }

  async function importTemplate(file: File) {
    setBusy("import");
    setError("");
    try {
      if (file.size > 262144)
        throw new Error("Template files must be smaller than 256 KiB.");
      const value: unknown = JSON.parse(await file.text());
      const item = await api<TemplateEntry>(
        `/workspaces/${workspaceId}/templates/import`,
        { method: "POST", body: JSON.stringify(value) },
      );
      setItems((items) => [item, ...items]);
    } catch (cause) {
      setError(
        cause instanceof Error
          ? cause.message
          : "Could not import this template.",
      );
    } finally {
      setBusy("");
    }
  }

  async function changeSharing(item: TemplateEntry, visibility: string) {
    setBusy(item.key);
    setError("");
    try {
      const updated = await api<TemplateEntry>(`/templates/${item.key}`, {
        method: "PATCH",
        body: JSON.stringify({ visibility }),
      });
      setItems(items.map((row) => (row.key === item.key ? updated : row)));
    } catch (cause) {
      setError(
        cause instanceof Error ? cause.message : "Could not change sharing.",
      );
    } finally {
      setBusy("");
    }
  }

  async function showPreview(item: TemplateEntry) {
    setBusy(item.key);
    setError("");
    try {
      setPreview(await api(`/templates/${item.key}`));
    } catch (cause) {
      setError(
        cause instanceof Error ? cause.message : "Could not preview template.",
      );
    } finally {
      setBusy("");
    }
  }

  async function instantiateTemplate(item: TemplateEntry) {
    setBusy(item.key);
    setError("");
    try {
      const result = await api<{ kind: "agent" | "workflow"; id: string }>(
        `/workspaces/${workspaceId}/templates/${item.key}/instantiate`,
        { method: "POST" },
      );
      router.push(
        result.kind === "agent"
          ? `/w/${workspaceId}/agents/${result.id}`
          : `/w/${workspaceId}/workflows/${result.id}/edit`,
      );
    } catch (cause) {
      setError(
        cause instanceof Error ? cause.message : "Could not create this draft.",
      );
      setBusy("");
    }
  }

  return (
    <>
      <PageHeader
        eyebrow="START WITH A PATTERN"
        title="Templates"
        description="Create from a starter or a shared template, then make the copy your own."
      />
      {error && <ErrorNotice message={error} />}
      <div className="template-intro">
        <Sparkles size={18} />
        <span>
          Templates create editable drafts. Choose a provider and model before
          publishing an agent. Connect required agent versions and service
          tools, validate the workflow, then publish and run.
        </span>
      </div>
      <p>
        Save your own templates from an agent or workflow editor. Shared
        templates create independent drafts; configure connections before
        running.
      </p>
      <div className="template-transfer">
        <Upload size={16} />
        <label htmlFor="template-import">
          Import a FlowForge template
          <input
            id="template-import"
            type="file"
            accept=".json,application/json"
            disabled={!canCreate || !!busy}
            onChange={(event) => {
              const file = event.target.files?.[0];
              event.target.value = "";
              if (file) void importTemplate(file);
            }}
          />
        </label>
        <p>
          Imports are private. Connections and credentials must be configured
          again. Review instructions and fixed text before sharing exported
          files.
        </p>
      </div>
      {preview && (
        <section
          className="panel"
          aria-label="Template preview"
          style={{ padding: 24 }}
        >
          <div className="row between">
            <h2>{preview.name}</h2>
            <Button variant="ghost" onClick={() => setPreview(null)}>
              Close preview
            </Button>
          </div>
          {preview.config && (
            <p style={{ whiteSpace: "pre-wrap" }}>
              {preview.config.instructions || "No instructions yet."}
            </p>
          )}
          {preview.graph && (
            <ol>
              {preview.graph.nodes.map((node) => (
                <li key={node.id}>
                  {node.label} / {node.type.replaceAll("_", " ")}
                </li>
              ))}
            </ol>
          )}
          {preview.setup_steps && (
            <>
              <h3>Set up this template</h3>
              <ol>
                {preview.setup_steps.map((step) => (
                  <li key={step}>{step}</li>
                ))}
              </ol>
            </>
          )}
          {preview.sample_input && (
            <>
              <h3>Sample input</h3>
              <pre className="tool-output">
                {JSON.stringify(preview.sample_input, null, 2)}
              </pre>
            </>
          )}
        </section>
      )}
      <div className="template-grid">
        {templatePresentation(items, focus).map(({ template: item, recommended }) => (
          <article key={item.key} className="panel template-card">
            <div className="row between">
              <span
                className={`node-icon ${item.kind === "agent" ? "purple" : "blue"}`}
              >
                {item.kind === "agent" ? (
                  <Bot size={22} />
                ) : (
                  <GitBranch size={22} />
                )}
              </span>
              <div className="row">
                {recommended && <Badge tone="green">Recommended</Badge>}
                <Badge tone="purple">{item.category}</Badge>
              </div>
            </div>
            <h2>{item.name}</h2>
            <p>{item.description}</p>
            <Badge>
              {item.visibility
                ? {
                    private: "Only me",
                    workspace: "Workspace",
                    public: "Community",
                  }[item.visibility]
                : "Built-in"}
            </Badge>
            {item.owned && (
              <label className="field">
                Sharing
                <select
                  aria-label={`Sharing for ${item.name}`}
                  value={item.visibility}
                  disabled={!!busy}
                  onChange={(e) => changeSharing(item, e.target.value)}
                >
                  <option value="private">Only me</option>
                  <option value="workspace">Workspace members</option>
                  <option value="public">Everyone signed in</option>
                </select>
              </label>
            )}
            <Button
              variant="ghost"
              disabled={!!busy}
              onClick={() => showPreview(item)}
            >
              Preview
            </Button>
            <Button
              variant="ghost"
              disabled={!!busy}
              onClick={() => exportTemplate(item)}
            >
              <Download size={14} />
              Export JSON
            </Button>
            <div className="template-footer">
              <span>
                {item.kind === "agent" ? "Agent starter" : "Workflow starter"} ·
                v{item.template_version}
              </span>
              <Button
                size="sm"
                disabled={!canCreate || !!busy}
                onClick={() => instantiateTemplate(item)}
              >
                {busy === item.key ? (
                  <LoaderCircle size={14} className="spin" />
                ) : (
                  <ArrowRight size={14} />
                )}
                Use template
              </Button>
            </div>
          </article>
        ))}
      </div>
    </>
  );
}
