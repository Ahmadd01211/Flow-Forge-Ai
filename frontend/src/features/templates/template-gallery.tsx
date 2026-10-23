"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import {
  ArrowRight,
  Bot,
  GitBranch,
  LoaderCircle,
  Sparkles,
} from "lucide-react";
import { Badge, ErrorNotice, PageHeader } from "@/components/shared/ui";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api/client";

export interface TemplateEntry {
  key: string;
  kind: "agent" | "workflow";
  name: string;
  description: string;
  category: string;
  template_version: number;
}

export function TemplateGallery({
  workspaceId,
  templates,
  canCreate,
}: {
  workspaceId: string;
  templates: TemplateEntry[];
  canCreate: boolean;
}) {
  const router = useRouter();
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");

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
        description="Copy a reviewed starter into your private workspace, then make it your own."
      />
      {error && <ErrorNotice message={error} />}
      <div className="template-intro">
        <Sparkles size={18} />
        <span>
          Templates create editable drafts. Choose a provider and model before
          publishing an agent; linear workflows with approved local tools can be
          published and run.
        </span>
      </div>
      <div className="template-grid">
        {templates.map((item) => (
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
              <Badge tone="purple">{item.category}</Badge>
            </div>
            <h2>{item.name}</h2>
            <p>{item.description}</p>
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
