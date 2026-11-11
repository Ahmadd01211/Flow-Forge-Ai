"use client";
import { useState } from "react";
import Link from "next/link";
import { Check, Copy, GitBranch, Globe2, MessageSquare } from "lucide-react";
import type { AgentConfig, AgentVersion } from "@/lib/api/types";
import { readFields } from "./schema-fields";
import { isChatInput } from "./builder-model";

/** An example input for the API snippet, shaped from the published input fields. */
export function exampleInput(schema: AgentConfig["input_schema"]): Record<string, unknown> {
  if (isChatInput(schema)) return { conversation_id: "customer-42", message: "Where is my order?" };
  const fields = readFields(JSON.stringify(schema)) ?? [];
  return Object.fromEntries(fields.map((field) => [field.name, field.enum?.[0] ?? (field.type === "string" ? "…" : field.type === "boolean" ? true : 1)]));
}

export function UsePanel({ workspaceId, agentId, published }: { workspaceId: string; agentId: string; published: AgentVersion | undefined }) {
  const [copied, setCopied] = useState(false);
  const base = `/w/${workspaceId}`;
  if (!published) return <p className="builder-hint">Publish a version first. Then you can chat with it, call it from your app, or use it in a workflow.</p>;
  const chatReady = isChatInput(published.config.input_schema);
  const origin = typeof window === "undefined" ? "https://your-flowforge" : window.location.origin;
  const snippet = [
    `curl -X POST ${origin}/api/v1/deployments/<DEPLOYMENT_ID>/invoke \\`,
    `  -H "Authorization: Bearer ff_live_…" \\`,
    `  -H "Idempotency-Key: $(uuidgen)" \\`,
    `  -H "Content-Type: application/json" \\`,
    `  -d '${JSON.stringify({ input: exampleInput(published.config.input_schema) })}'`,
  ].join("\n");
  return (
    <div className="use-panel">
      <div className="use-card">
        <MessageSquare size={18} />
        <div>
          <strong>Chat with it</strong>
          <small>{chatReady ? `Talk to v${published.number} in a full-page chat.` : "Needs the Chat input preset. Pick it in Input & output, then publish."}</small>
        </div>
        {chatReady && <Link className="text-link" href={`${base}/agents/${agentId}/chat`}>Open chat</Link>}
      </div>
      <div className="use-card">
        <GitBranch size={18} />
        <div>
          <strong>Use it in a workflow</strong>
          <small>Add an AI agent step and pick “{published.name} · v{published.number}”.</small>
        </div>
        <Link className="text-link" href={`${base}/workflows`}>Open workflows</Link>
      </div>
      <div className="use-card column">
        <div className="row">
          <Globe2 size={18} />
          <div>
            <strong>Call it from your app</strong>
            <small>Create a deployment for v{published.number} to get its ID and key, then send:</small>
          </div>
          <Link className="text-link" href={`${base}/deployments`}>Deployments</Link>
        </div>
        <pre className="use-snippet">{snippet}</pre>
        <button type="button" className="text-link" onClick={() => navigator.clipboard?.writeText(snippet).then(() => { setCopied(true); setTimeout(() => setCopied(false), 1500); })}>
          {copied ? <Check size={13} /> : <Copy size={13} />} {copied ? "Copied" : "Copy snippet"}
        </button>
      </div>
    </div>
  );
}
