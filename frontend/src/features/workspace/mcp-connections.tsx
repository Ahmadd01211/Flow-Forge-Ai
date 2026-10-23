"use client";

import { useState } from "react";
import { Check, Globe2, KeyRound, LoaderCircle, ShieldCheck } from "lucide-react";
import { Badge, ErrorNotice } from "@/components/shared/ui";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api/client";

export interface McpServer {
  id: string;
  name: string;
  allowed_tools: string[];
  verified_tools: string[];
  runnable_tools: string[];
  state: "not_connected" | "active" | "revoked";
  verified_at: string | null;
}

export function McpConnections({ workspaceId, initialServers, canManage, canTest }: {
  workspaceId: string;
  initialServers: McpServer[];
  canManage: boolean;
  canTest: boolean;
}) {
  const [servers, setServers] = useState(initialServers);
  const [selected, setSelected] = useState(initialServers[0]?.id || "");
  const [token, setToken] = useState("");
  const [selectedTool, setSelectedTool] = useState("");
  const [argumentsJson, setArgumentsJson] = useState("{}");
  const [output, setOutput] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const server = servers.find((item) => item.id === selected);
  const tool = server?.verified_tools.includes(selectedTool) ? selectedTool : server?.verified_tools[0] || "";
  const base = `/workspaces/${workspaceId}/mcp`;

  async function connect() {
    if (!server) return;
    setBusy(true); setError(""); setNotice("");
    try {
      const result = await api<{ items: McpServer[] }>(`${base}/${server.id}`, { method: "PUT", body: JSON.stringify({ bearer_token: token }) });
      setServers(result.items); setToken(""); setOutput("");
      setNotice("Server verified. Only operator-approved tools are available for testing.");
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Could not connect this MCP server."); }
    finally { setBusy(false); }
  }

  async function disconnect() {
    if (!server) return;
    setBusy(true); setError(""); setNotice("");
    try {
      const result = await api<{ items: McpServer[] }>(`${base}/${server.id}`, { method: "DELETE" });
      setServers(result.items); setSelectedTool(""); setOutput(""); setNotice("Connection revoked and its stored token removed.");
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Could not revoke this MCP server."); }
    finally { setBusy(false); }
  }

  async function test() {
    if (!server || !tool) return;
    setBusy(true); setError(""); setOutput("");
    try {
      const parsed: unknown = JSON.parse(argumentsJson);
      if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) throw new Error("Arguments must be a JSON object.");
      const result = await api<{ output: unknown }>(`${base}/${server.id}/tools/${encodeURIComponent(tool)}/test`, { method: "POST", body: JSON.stringify({ arguments: parsed }) });
      setOutput(JSON.stringify(result.output, null, 2));
    } catch (cause) { setError(cause instanceof Error ? cause.message : "MCP tool test failed."); }
    finally { setBusy(false); }
  }

  return <section className="panel mcp-panel">
    <div className="mcp-heading"><div><span className="integration-eyebrow">REMOTE CAPABILITIES</span><h2>MCP servers</h2><p>Connect a reviewed external service and inspect its approved read-only tools.</p></div><Badge tone="purple">{servers.filter((item) => item.state === "active").length} connected</Badge></div>
    {!servers.length ? <div className="mcp-empty"><Globe2 size={24} /><div><strong>No MCP servers are configured</strong><p>A platform operator must add and review an HTTPS server before workspaces can connect it.</p></div></div> : <div className="mcp-layout">
      <div className="mcp-server-list">{servers.map((item) => <button type="button" key={item.id} className={selected === item.id ? "selected" : ""} onClick={() => { setSelected(item.id); setToken(""); setSelectedTool(""); setOutput(""); setError(""); setNotice(""); }}><Globe2 size={18} /><span><strong>{item.name}</strong><small>{item.state === "active" ? `${item.verified_tools.length} approved tools` : "Not connected"}</small></span><Badge tone={item.state === "active" ? "green" : "amber"}>{item.state === "active" ? "Connected" : "Available"}</Badge></button>)}</div>
      {server && <div className="mcp-detail">
        <div className="row between"><h3>{server.name}</h3><Badge tone={server.state === "active" ? "green" : "amber"}>{server.state === "active" ? "Verified" : "Awaiting connection"}</Badge></div>
        <p>Allowed tools: {server.allowed_tools.join(", ")}. Workflow-ready read-only tools: {server.runnable_tools?.join(", ") || "none"}. Remote descriptions do not grant additional permissions.</p>
        {error && <ErrorNotice message={error} />}
        {notice && <div className="integration-notice"><Check size={16} /> {notice}</div>}
        {canManage && <div className="mcp-credential"><label htmlFor="mcp-token">Bearer token <small>Leave blank for a public server</small></label><div className="integration-key-row"><div className="integration-key-input"><KeyRound size={16} /><input id="mcp-token" type="password" autoComplete="off" value={token} onChange={(event) => setToken(event.target.value)} placeholder="Optional server token" /></div><Button disabled={busy} onClick={connect}>{busy ? <LoaderCircle size={15} className="spin" /> : <ShieldCheck size={15} />}{server.state === "active" ? "Verify or rotate" : "Connect server"}</Button></div>{server.state === "active" && <button className="mcp-revoke" type="button" disabled={busy} onClick={disconnect}>Revoke connection</button>}</div>}
        {server.state === "active" && <div className="mcp-test"><h4>Test approved tool</h4><label htmlFor="mcp-tool">Tool</label><select id="mcp-tool" value={tool} onChange={(event) => { setSelectedTool(event.target.value); setOutput(""); }}>{server.verified_tools.map((name) => <option key={name} value={name}>{name}</option>)}</select><label htmlFor="mcp-arguments">Arguments JSON</label><textarea id="mcp-arguments" className="run-input" spellCheck={false} value={argumentsJson} onChange={(event) => setArgumentsJson(event.target.value)} /><Button disabled={busy || !canTest || !tool} onClick={test}>Run tool test</Button>{output && <><label htmlFor="mcp-output">Response JSON</label><pre id="mcp-output" className="tool-output">{output}</pre></>}</div>}
      </div>}
    </div>}
  </section>;
}
