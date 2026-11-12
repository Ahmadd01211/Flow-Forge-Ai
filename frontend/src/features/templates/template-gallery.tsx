"use client";

import { useRef, useState } from "react";
import Link from "next/link";
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
import type { GraphNode } from "@/lib/api/types";
import { discoverRecipes } from "@/features/workspace/task-start-model";
import { requiresPublishedRun } from "@/features/workflows/node-config";

export interface TemplateEntry {
  key: string;
  kind: "agent" | "workflow";
  name: string;
  description: string;
  category: string;
  template_version: number;
  visibility?: "private" | "workspace" | "public";
  owned?: boolean;
  setup_steps?: string[];
  sample_input?: Record<string, unknown>;
  expected_result?: string;
  starter_skills?: string[];
}

interface RecipeDetail extends TemplateEntry {
  config?: { instructions?: string };
  graph?: { nodes: Pick<GraphNode, "id" | "label" | "type" | "config">[] };
}

interface CreatedDraft {
  kind: "agent" | "workflow";
  id: string;
  template_key?: string;
  skill_ids?: string[];
}

function skillLabel(key: string) {
  return key.replaceAll("-", " ");
}

function RunGuidance({ recipe }: { recipe: RecipeDetail }) {
  if (recipe.kind === "agent")
    return (
      <p>
        Connect a provider and choose a model before testing. Model tests can
        incur provider charges; review the model pricing and run limits in the
        editor.
      </p>
    );
  if (recipe.graph && !requiresPublishedRun(recipe.graph.nodes, []))
    return (
      <p>
        Use local draft preview in the workflow editor with the sample input.
        Preview does not create a durable full run. Review validation and
        publish when ready for durable runs.
      </p>
    );
  return (
    <p>
      Publish before a durable full run. Agent, model, external service and
      pause steps require publication; local draft preview is limited to
      supported local steps. Configure referenced published agents and
      connections, review run caps and provider charges, and confirm any
      external actions in the editor.
    </p>
  );
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
  const [items, setItems] = useState(templates);
  const [preview, setPreview] = useState<RecipeDetail | null>(null);
  const [created, setCreated] = useState<CreatedDraft | null>(null);
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState("all");
  const previewHeading = useRef<HTMLHeadingElement>(null);
  const previewTrigger = useRef<HTMLButtonElement | null>(null);
  const createdHeading = useRef<HTMLHeadingElement>(null);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const recipes = discoverRecipes(items, query, category, focus);

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
      const detail = await api<RecipeDetail>(`/templates/${item.key}`);
      setPreview(detail);
      setCreated(null);
      requestAnimationFrame(() => previewHeading.current?.focus());
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
      const result = await api<CreatedDraft>(
        `/workspaces/${workspaceId}/templates/${item.key}/instantiate`,
        { method: "POST" },
      );
      setCreated({ ...result, template_key: result.template_key || item.key });
      requestAnimationFrame(() => createdHeading.current?.focus());
    } catch (cause) {
      setError(
        cause instanceof Error ? cause.message : "Could not create this draft.",
      );
    } finally {
      setBusy("");
    }
  }

  return (
    <>
      <PageHeader
        eyebrow="START WITH A TASK"
        title="Task recipes"
        description="Choose a task, preview its setup and result, then create an editable workspace draft."
      />
      {error && <ErrorNotice message={error} />}
      <div className="template-intro">
        <Sparkles size={18} />
        <span>
          Created drafts are workspace-visible under your workspace access
          rules. Browsing and previewing a recipe do not call a model or run its
          steps.
        </span>
      </div>
      <p>
        Save your own templates from an agent or workflow editor. Shared
        templates create independent drafts; configure connections before
        running.
      </p>
      <details>
        <summary>Advanced template import and export</summary>
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
            Imported templates are visible only to you; drafts created from them
            are workspace-visible. Configure connections and credentials again.
            Review instructions and fixed text before sharing exports.
          </p>
        </div>
        <p>
          Export JSON from any recipe card. Save your own templates in the
          existing agent or workflow editor.
        </p>
      </details>
      <div className="template-transfer">
        <label className="field" htmlFor="recipe-search">
          Search recipes
          <input
            id="recipe-search"
            type="search"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Describe a task, such as customer reply"
          />
        </label>
        <label className="field" htmlFor="recipe-category">
          Category
          <select
            id="recipe-category"
            value={category}
            onChange={(event) => setCategory(event.target.value)}
          >
            <option value="all">All categories</option>
            {[...new Set(items.map((item) => item.category))]
              .sort()
              .map((value) => (
                <option key={value} value={value}>
                  {value}
                </option>
              ))}
          </select>
        </label>
      </div>
      {created && preview && (
        <section
          className="panel"
          aria-label="Created workspace draft"
          style={{ padding: 24 }}
        >
          <h2 ref={createdHeading} tabIndex={-1}>
            Workspace draft created: {preview.name}
          </h2>
          <p role="status">
            Your editable draft is workspace-visible. It has not been published
            or run.
          </p>
          {!!created.skill_ids?.length && (
            <>
              <p>
                Review and publish every attached skill before you test or
                publish the agent. After edits, publish a new immutable skill
                version, then review the agent readiness again.
              </p>
              <ul>
                {created.skill_ids.map((id, index) => (
                  <li key={id}>
                    <Link href={`/w/${workspaceId}/agents/skills/${id}`}>
                      Review attached skill:{" "}
                      {preview.starter_skills?.[index]
                        ? skillLabel(preview.starter_skills[index])
                        : `Skill ${index + 1}`}
                    </Link>
                  </li>
                ))}
              </ul>
              <Link href={`/w/${workspaceId}/agents/skills`}>
                Open skill library
              </Link>
            </>
          )}
          <RunGuidance recipe={preview} />
          <p>
            {preview.sample_input
              ? "Continue setup with this recipe's sample input and expected example. Review them before testing."
              : "No sample input supplied. Enter your own safe sample in the editor before testing."}
          </p>
          <Button asChild>
            <Link
              href={
                created.kind === "agent"
                  ? `/w/${workspaceId}/agents/${created.id}?recipe=${encodeURIComponent(created.template_key || preview.key)}`
                  : `/w/${workspaceId}/workflows/${created.id}/edit?recipe=${encodeURIComponent(created.template_key || preview.key)}`
              }
            >
              Continue setup <ArrowRight size={14} />
            </Link>
          </Button>
        </section>
      )}
      {preview && !created && (
        <section
          className="panel"
          aria-label="Recipe preview"
          style={{ padding: 24 }}
        >
          <div className="row between">
            <h2 ref={previewHeading} tabIndex={-1}>
              {preview.name}
            </h2>
            <Button
              variant="ghost"
              disabled={!!busy}
              onClick={() => {
                setPreview(null);
                previewTrigger.current?.focus();
              }}
            >
              Close preview
            </Button>
          </div>
          <p>{preview.description}</p>
          <p>
            Creates a workspace-visible {preview.kind} draft. Review it with
            your team before publishing.
          </p>
          <h3>Expected result</h3>
          <p>
            {preview.expected_result ||
              preview.description ||
              "Review this recipe in the editor to define its intended result."}
          </p>
          <h3>Required setup</h3>
          {!!preview.setup_steps?.length && (
            <ol>
              {preview.setup_steps.map((step) => (
                <li key={step}>{step}</li>
              ))}
            </ol>
          )}
          {!preview.setup_steps?.length && (
            <p>
              Review the instructions, required connections and validation in
              the editor before testing.
            </p>
          )}
          <RunGuidance recipe={preview} />
          <p>
            Permissions: creation does not grant tool access or copy
            credentials. Review tool permissions and any action confirmations
            before running.
          </p>
          {!!preview.starter_skills?.length && (
            <>
              <h3>Skills copied as editable drafts</h3>
              <ul>
                {preview.starter_skills.map((key) => (
                  <li key={key}>{skillLabel(key)}</li>
                ))}
              </ul>
              <p>
                Review and publish these skills before testing or publishing the
                agent. After skill edits, publish a new immutable version and
                check agent readiness again.
              </p>
            </>
          )}
          <details>
            <summary>Recipe instructions and steps</summary>
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
          </details>
          {preview.sample_input && (
            <>
              <h3>Sample input</h3>
              <pre className="tool-output">
                {JSON.stringify(preview.sample_input, null, 2)}
              </pre>
            </>
          )}
          {!preview.sample_input && (
            <p>No sample input supplied. Add safe sample data in the editor.</p>
          )}
          <Button
            disabled={!canCreate || !!busy}
            onClick={() => instantiateTemplate(preview)}
          >
            {busy === preview.key ? (
              <LoaderCircle size={14} className="spin" />
            ) : (
              <ArrowRight size={14} />
            )}
            Create workspace draft
          </Button>
          {!canCreate && (
            <p>A workspace editor or admin can create this draft.</p>
          )}
        </section>
      )}
      <div className="template-grid">
        {recipes.map(({ template: item, recommended }) => (
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
                {item.key === "remove-duplicates" &&
                  item.kind === "workflow" &&
                  !item.visibility && (
                    <Badge tone="green">Try without a model</Badge>
                  )}
                {recommended && <Badge tone="green">Recommended</Badge>}
                <Badge tone="purple">{item.category}</Badge>
              </div>
            </div>
            <h2>{item.name}</h2>
            <p>{item.description}</p>
            <p>
              Required setup:{" "}
              {item.kind === "agent"
                ? "provider, model and review of attached skills"
                : "review steps, connections and run readiness"}
              .
            </p>
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
              aria-label={`Preview ${item.name}`}
              disabled={!!busy}
              onClick={(event) => {
                previewTrigger.current = event.currentTarget;
                void showPreview(item);
              }}
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
            </div>
          </article>
        ))}
      </div>
      {recipes.length === 0 && (
        <p role="status">
          No recipes match. Try another task or choose all categories.
        </p>
      )}
    </>
  );
}
