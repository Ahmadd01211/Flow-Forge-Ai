"use client";

import { useState } from "react";
import { Code2, LoaderCircle, ShieldCheck } from "lucide-react";
import { Badge, ErrorNotice, PageHeader } from "@/components/shared/ui";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api/client";

export interface ToolEntry {
  key: string;
  name: string;
  description: string;
  input_schema: Record<string, unknown>;
  read_only: boolean;
  installed: boolean;
}

const examples: Record<string, string> = {
  "json.extract": '{"document":{"customer":{"email":"alex@example.com"}},"pointer":"/customer/email"}',
  "text.replace": '{"text":"Hello world","find":"world","replacement":"FlowForge"}',
};

export function ToolRegistry({ workspaceId, initialTools, canManage, canTest }: {
  workspaceId: string;
  initialTools: ToolEntry[];
  canManage: boolean;
  canTest: boolean;
}) {
  const [tools, setTools] = useState(initialTools);
  const [selected, setSelected] = useState(initialTools[0]?.key || "");
  const [input, setInput] = useState(examples[selected] || "{}");
  const [output, setOutput] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const tool = tools.find((item) => item.key === selected);
  const base = `/workspaces/${workspaceId}/tools/${selected}`;

  async function setApproval(installed: boolean) {
    setBusy(true);
    setError("");
    try {
      await api(base, { method: installed ? "PUT" : "DELETE" });
      setTools((items) => items.map((item) => item.key === selected ? { ...item, installed } : item));
      setOutput("");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not update this tool.");
    } finally {
      setBusy(false);
    }
  }

  async function test() {
    setBusy(true);
    setError("");
    setOutput("");
    try {
      const parsed: unknown = JSON.parse(input);
      if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) throw new Error("Input must be a JSON object.");
      const result = await api<{ output: unknown }>(`${base}/test`, { method: "POST", body: JSON.stringify({ input: parsed }) });
      setOutput(JSON.stringify(result.output, null, 2));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not test this tool.");
    } finally {
      setBusy(false);
    }
  }

  return <>
    <PageHeader eyebrow="REVIEWED CAPABILITIES" title="Tool Registry" description="Approve bounded tools for this workspace and test them before using them in an agent or workflow." />
    <div className="tool-registry-layout">
      <section className="panel tool-registry-list" aria-label="Available tools">
        <div className="tool-section-heading"><h2>Available tools</h2><Badge tone="purple">{tools.length}</Badge></div>
        {tools.map((item) => <button type="button" key={item.key} className={`tool-row ${selected === item.key ? "selected" : ""}`} onClick={() => { setSelected(item.key); setInput(examples[item.key] || "{}"); setOutput(""); setError(""); }}>
          <span className="node-icon purple"><Code2 size={18} /></span>
          <span><strong>{item.name}</strong><small>{item.key}</small></span>
          <Badge tone={item.installed ? "green" : "amber"}>{item.installed ? "Approved" : "Available"}</Badge>
        </button>)}
      </section>
      {tool && <section className="panel tool-registry-detail">
        <div className="row between"><div><span className="integration-eyebrow">{tool.key}</span><h2>{tool.name}</h2></div><Badge tone="green">Read only</Badge></div>
        <p>{tool.description}</p>
        <div className="tool-security-note"><ShieldCheck size={18} /><span>This reviewed handler has no network, filesystem, or credential access. Approval is scoped to this workspace.</span></div>
        {error && <ErrorNotice message={error} />}
        {canManage && <div className="tool-actions"><Button disabled={busy} variant={tool.installed ? "outline" : "default"} onClick={() => setApproval(!tool.installed)}>{busy ? <LoaderCircle size={15} className="spin" /> : <ShieldCheck size={15} />}{tool.installed ? "Remove approval" : "Approve for workspace"}</Button></div>}
        <div className="tool-test"><h3>Test tool</h3><p>Enter JSON matching the input schema. Test output is shown here only and is not saved.</p>
          <label htmlFor="tool-input">Input JSON</label><textarea id="tool-input" className="run-input" value={input} onChange={(event) => setInput(event.target.value)} spellCheck={false} />
          <Button disabled={busy || !tool.installed || !canTest} onClick={test}>Run test</Button>
          {!tool.installed && <small>Approve this tool before testing.</small>}
          {output && <><label htmlFor="tool-output">Output JSON</label><pre id="tool-output" className="tool-output">{output}</pre></>}
        </div>
      </section>}
    </div>
  </>;
}
