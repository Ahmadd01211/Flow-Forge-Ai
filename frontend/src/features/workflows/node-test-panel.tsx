"use client";
import { useState } from "react";
import { AlertCircle, CheckCircle2, ExternalLink, FlaskConical, LoaderCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/shared/ui";
import { api } from "@/lib/api/client";
import type { AgentRunSummary, Graph, GraphNode, NodeTestResult } from "@/lib/api/types";
import { reshapes, resultSources, selectedPathLabel } from "./node-config";

export type NodeTestState = {
  input?: string;
  outputs?: string;
  result?: NodeTestResult;
  /** Config the result was produced with, to flag results that predate an edit. */
  configKey?: string;
};

const ENTRY = ["manual_input", "webhook_trigger", "schedule_trigger", "chat_trigger"];
const pretty = (value: unknown) => JSON.stringify(value ?? null, null, 2);

export function NodeTestPanel({ workspaceId, workflowId, graph, node, tests, setTest, sampleInput, blocked, externalTarget }: {
  workspaceId: string;
  workflowId: string;
  graph: Graph;
  node: GraphNode;
  tests: Record<string, NodeTestState>;
  setTest: (nodeId: string, update: NodeTestState) => void;
  /** The workflow-level sample input from the preview panel. */
  sampleInput: string;
  /** Why this node cannot be tested yet (its own configuration errors), if anything. */
  blocked: string | null;
  /** Human description of the outside service this step calls, for external steps. */
  externalTarget: string | null;
}) {
  const state = tests[node.id] ?? {};
  const [busy, setBusy] = useState(false), [error, setError] = useState(""), [confirmed, setConfirmed] = useState(false);
  const label = (id: string) => graph.nodes.find((item) => item.id === id)?.label ?? id;
  const outputOf = (id: string): unknown => {
    if (ENTRY.includes(graph.nodes.find((item) => item.id === id)?.type ?? "")) {
      try { return JSON.parse(sampleInput); } catch { return undefined; }
    }
    const result = tests[id]?.result;
    return result?.status === "completed" ? result.output : undefined;
  };

  const incoming = graph.edges.filter((edge) => edge.target === node.id);
  const suggestions = incoming.flatMap((edge) => {
    const output = outputOf(edge.source);
    return output === undefined ? [] : [{ id: edge.source, text: pretty(output), mapped: reshapes(edge.mappings) }];
  });
  const sources = resultSources(node);
  const inputText = state.input ?? suggestions[0]?.text ?? (ENTRY.includes(node.type) ? sampleInput : "{}");
  const outputsText = state.outputs ?? pretty(Object.fromEntries(sources.map((id) => [id, outputOf(id) ?? null])));
  const missingSources = sources.filter((id) => outputOf(id) === undefined);
  const configKey = JSON.stringify(node.config);
  const external = externalTarget !== null;

  async function poll(run: AgentRunSummary, result: NodeTestResult) {
    for (let i = 0; i < 60 && (run.state === "queued" || run.state === "running"); i++) {
      await new Promise((resolve) => setTimeout(resolve, 1000));
      run = await api<AgentRunSummary>(`/workspaces/${workspaceId}/runs/${run.id}`);
      setTest(node.id, { result: { ...result, agent_run: run }, configKey });
    }
    const status = run.state === "completed" ? "completed" : run.state === "queued" || run.state === "running" ? "queued" : "failed";
    setTest(node.id, {
      configKey,
      result: {
        ...result, agent_run: run, status, output: run.output,
        error: status === "failed" ? { code: run.error_code ?? run.state.toUpperCase(), message: `The agent run ${run.state}.` } : null,
      },
    });
  }

  async function run() {
    setError("");
    let input: unknown, outputs: unknown = {};
    try {
      input = JSON.parse(inputText);
      if (sources.length) outputs = JSON.parse(outputsText);
    } catch {
      setError("Sample input and step outputs must be valid JSON.");
      return;
    }
    setBusy(true);
    try {
      const result = await api<NodeTestResult>(`/workspaces/${workspaceId}/workflows/${workflowId}/nodes/${node.id}/test`, {
        method: "POST",
        headers: node.type === "agent" || node.type === "llm" ? { "Idempotency-Key": crypto.randomUUID() } : {},
        body: JSON.stringify({ graph, input, outputs, confirm_external: external && confirmed }),
      });
      setTest(node.id, { input: inputText, outputs: sources.length ? outputsText : undefined, result, configKey });
      if (result.agent_run) await poll(result.agent_run, result);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "The test could not run.");
    } finally {
      setBusy(false);
    }
  }

  const result = state.result;
  return (
    <div className="node-test">
      <p className="node-form-hint">
        Runs only this step on the sample below, using the settings in the editor. Nothing is saved and no workflow run is created.
      </p>
      {suggestions.length > 0 && (
        <div className="placeholder-chips">
          {suggestions.map((item) => (
            <button type="button" key={item.id} className="chip-button" onClick={() => setTest(node.id, { input: item.text })}>
              Use output of {label(item.id)}
            </button>
          ))}
          {suggestions.some((item) => item.mapped) && <span className="node-form-hint">Connection mappings are applied in runs, not to this sample.</span>}
        </div>
      )}
      <label>
        {ENTRY.includes(node.type) ? "Workflow input (JSON)" : "Data arriving at this step (JSON)"}
        <textarea className="json-editor" spellCheck={false} rows={8} value={inputText} onChange={(event) => setTest(node.id, { input: event.target.value })} />
      </label>
      {sources.length > 0 && (
        <label>
          Earlier step outputs (JSON, by step ID)
          <textarea className="json-editor" spellCheck={false} rows={6} value={outputsText} onChange={(event) => setTest(node.id, { outputs: event.target.value })} />
          {missingSources.length > 0 && !state.outputs && (
            <span className="node-form-hint">Test {missingSources.map(label).join(", ")} first to fill these in, or enter sample outputs.</span>
          )}
        </label>
      )}
      {external && (
        <div className="permission-callout">
          <ExternalLink size={17} />
          <div>
            <p><strong>This test calls {externalTarget}.</strong> {node.type === "agent" || node.type === "llm"
              ? "It becomes a normal agent run: the agent's budget and the workspace limit of two active runs apply, and usage is recorded."
              : "Only read-only tools can be tested here; write tools run in a published workflow. Tests share the 20-per-minute MCP limit and are recorded in the audit log."}</p>
            <label className="checkbox-row">
              <input type="checkbox" checked={confirmed} onChange={(event) => setConfirmed(event.target.checked)} />
              I want to make this external call
            </label>
          </div>
        </div>
      )}
      {blocked && <p className="field-error"><AlertCircle size={11} /> {blocked}</p>}
      {error && <p className="field-error"><AlertCircle size={11} /> {error}</p>}
      <Button size="sm" onClick={run} disabled={busy || !!blocked || (external && !confirmed)}>
        {busy ? <LoaderCircle size={14} className="spin" /> : <FlaskConical size={14} />}
        {external ? "Run external test" : "Run test"}
      </Button>
      {result && (
        <div className={`node-test-result ${result.status}`} aria-live="polite">
          <div className="row">
            {result.status === "completed" ? <CheckCircle2 size={14} /> : result.status === "failed" ? <AlertCircle size={14} /> : <LoaderCircle size={14} className="spin" />}
            <strong>{result.status === "queued" ? `Agent run ${result.agent_run?.state ?? "queued"}` : result.status === "completed" ? "Passed" : "Failed"}</strong>
            {result.selected_port && <Badge tone={node.type === "condition" && result.selected_port === "true" ? "green" : "amber"}>{selectedPathLabel(result.selected_port, node)}</Badge>}
            {result.status !== "queued" && !result.agent_run && <span className="muted">{result.duration_ms} ms</span>}
          </div>
          {state.configKey !== configKey && <p className="node-form-hint">Settings changed since this test. Run it again to check them.</p>}
          {result.error && <p className="field-error"><code>{result.error.code}</code> {result.error.message}</p>}
          {result.agent_run && (
            <p className="node-form-hint">
              {result.agent_run.cost_usd
                ? `Cost $${result.agent_run.cost_usd} · ${result.agent_run.input_tokens} input / ${result.agent_run.output_tokens} output tokens`
                : `Up to $${result.agent_run.reserved_max_usd} reserved`}
              {result.agent_run.uncertain_cost_usd && ` · provider outcome uncertain, possible charge up to $${result.agent_run.uncertain_cost_usd}`}
            </p>
          )}
          {result.status === "completed" && <pre className="tool-output">{pretty(result.output)}</pre>}
        </div>
      )}
    </div>
  );
}
