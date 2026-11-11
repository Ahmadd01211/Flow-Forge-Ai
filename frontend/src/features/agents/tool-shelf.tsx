"use client";
import { useState } from "react";
import Link from "next/link";
import { Globe2, Plug, Plus, Wrench } from "lucide-react";
import type { AgentConfig } from "@/lib/api/types";
import type { ToolEntry } from "@/features/tools/tool-registry";
import type { HttpTool } from "@/features/tools/http-tool-registry";
import type { McpServerOption } from "./model-tools";
import { Switch } from "./builder-blocks";

type Grants = Pick<AgentConfig, "tool_keys" | "mcp_tools" | "http_tools">;
type Tile = { id: string; kind: "builtin" | "mcp" | "http"; label: string; on: number; total: number };

/** Tools as app tiles: open a tile to flip its individual tools on or off. */
export function ToolShelf({ grants: config, setGrants, supported, unsupportedNote, tools, mcpServers, httpTools, canEdit, workspaceId, onConnect }: {
  grants: Grants;
  setGrants: (grants: Grants) => void;
  /** False when the chosen model can't call tools; switches are then locked. */
  supported: boolean;
  unsupportedNote?: string;
  tools: ToolEntry[];
  mcpServers: McpServerOption[];
  httpTools: HttpTool[];
  canEdit: boolean;
  workspaceId: string;
  onConnect?: () => void;
}) {
  const apis = httpTools.filter((tool) => tool.state === "active" && tool.read_only && tool.method === "GET");
  const tiles: Tile[] = [
    { id: "builtin", kind: "builtin", label: "Built-in", on: config.tool_keys.length, total: tools.length },
    ...mcpServers.filter((server) => server.runnable_tools.length).map((server) => ({
      id: server.id, kind: "mcp" as const, label: server.name,
      on: config.mcp_tools.filter((grant) => grant.server_id === server.id).length, total: server.runnable_tools.length,
    })),
    ...(apis.length ? [{ id: "http", kind: "http" as const, label: "APIs", on: config.http_tools.length, total: apis.length }] : []),
  ];
  const [open, setOpen] = useState(tiles.find((tile) => tile.on)?.id ?? tiles[0].id);
  const active = tiles.find((tile) => tile.id === open) ?? tiles[0];
  const update = (next: Partial<Grants>) => setGrants({ tool_keys: config.tool_keys, mcp_tools: config.mcp_tools, http_tools: config.http_tools, ...next });
  const locked = !canEdit || !supported;
  const lost = [
    ...config.mcp_tools.filter((grant) => !mcpServers.some((server) => server.id === grant.server_id && server.runnable_tools.includes(grant.tool_name))).map((grant) => ({ key: `${grant.server_id}/${grant.tool_name}`, drop: () => update({ mcp_tools: config.mcp_tools.filter((item) => item !== grant) }) })),
    ...config.http_tools.filter((grant) => !apis.some((tool) => tool.id === grant.tool_id)).map((grant) => ({ key: grant.name || grant.tool_id, drop: () => update({ http_tools: config.http_tools.filter((item) => item !== grant) }) })),
  ];
  return (
    <>
      {!supported && unsupportedNote && <p className="builder-hint warn">{unsupportedNote}</p>}
      <div className="tool-shelf">
        {tiles.map((tile) => (
          <button key={tile.id} type="button" className={`tool-tile ${open === tile.id ? "selected" : ""} ${tile.on ? "active" : ""}`} aria-expanded={open === tile.id} onClick={() => setOpen(tile.id)}>
            <span className="tool-tile-icon">{tile.kind === "builtin" ? <Wrench size={18} /> : tile.kind === "mcp" ? <Plug size={18} /> : <Globe2 size={18} />}</span>
            <strong>{tile.label}</strong>
            <small>{tile.on ? `${tile.on} of ${tile.total} on` : `${tile.total} available`}</small>
          </button>
        ))}
        <button type="button" className="tool-tile add" onClick={onConnect} disabled={!onConnect}>
          <span className="tool-tile-icon"><Plus size={18} /></span>
          <strong>Connect</strong>
          <small>MCP server or app</small>
        </button>
      </div>
      <div className="tool-switches">
        {active.kind === "builtin" &&
          (tools.length ? tools.map((tool) => {
            const key = tool.key as AgentConfig["tool_keys"][number];
            const on = config.tool_keys.includes(key);
            return (
              <ToolRow key={tool.key} name={tool.name} note={tool.installed ? tool.description : "Approve it in the Tool Registry first"} badge="read-only" on={on} disabled={locked || (!on && !tool.installed)}
                onChange={(next) => update({ tool_keys: next ? [...config.tool_keys, key] : config.tool_keys.filter((item) => item !== key) })} />
            );
          }) : <p className="builder-hint">No reviewed tools yet. <Link className="text-link" href={`/w/${workspaceId}/tools`}>Open the Tool Registry</Link></p>)}
        {active.kind === "mcp" && mcpServers.find((server) => server.id === active.id)?.runnable_tools.map((name) => {
          const server = mcpServers.find((item) => item.id === active.id)!;
          const on = config.mcp_tools.some((grant) => grant.server_id === server.id && grant.tool_name === name);
          const readOnly = server.tools?.find((tool) => tool.name === name)?.read_only;
          return (
            <ToolRow key={name} name={name} note={readOnly ? "Reads data" : "Can change data in this service"} badge={readOnly ? "read-only" : "writes"} on={on} disabled={locked || (!on && config.mcp_tools.length >= 8)}
              onChange={(next) => update({ mcp_tools: next ? [...config.mcp_tools, { server_id: server.id, tool_name: name, description: "", input_schema: {} }] : config.mcp_tools.filter((grant) => grant.server_id !== server.id || grant.tool_name !== name) })} />
          );
        })}
        {active.kind === "http" && apis.map((tool) => {
          const on = config.http_tools.some((grant) => grant.tool_id === tool.id);
          return (
            <ToolRow key={tool.id} name={tool.name} note={tool.description || tool.url} badge="read-only" on={on} disabled={locked || (!on && config.http_tools.length >= 8)}
              onChange={(next) => update({ http_tools: next ? [...config.http_tools, { tool_id: tool.id, name: tool.name, description: tool.description, input_schema: {} }] : config.http_tools.filter((grant) => grant.tool_id !== tool.id) })} />
          );
        })}
      </div>
      {lost.map((item) => (
        <p key={item.key} className="builder-hint warn">
          {item.key} is no longer available. <button type="button" className="text-link" disabled={!canEdit} onClick={item.drop}>Remove it</button>
        </p>
      ))}
      <p className="builder-hint">Publishing pins each tool&apos;s contract and connection. Tools that write can change data in the connected service.</p>
    </>
  );
}

function ToolRow({ name, note, badge, on, disabled, onChange }: { name: string; note: string; badge: "read-only" | "writes"; on: boolean; disabled: boolean; onChange: (on: boolean) => void }) {
  return (
    <div className={`tool-row ${on ? "on" : ""}`}>
      <span className="tool-row-main">
        <strong>{name}</strong>
        <small>{note}</small>
      </span>
      <em className={`tool-badge ${badge === "writes" ? "writes" : ""}`}>{badge}</em>
      <Switch label={`Use ${name}`} checked={on} disabled={disabled} onChange={onChange} />
    </div>
  );
}
