"use client";

import { useMemo, useState, type KeyboardEvent } from "react";
import Link from "next/link";
import type { McpServerOption } from "@/features/agents/model-tools";
import {
  filterMcpToolOptions,
  mcpToolConfig,
  mcpToolOptions,
  nextMcpToolIndex,
} from "./mcp-tool-picker-model";

export function McpToolPicker({
  workspaceId,
  servers,
  value,
  onChange,
}: {
  workspaceId: string;
  servers: McpServerOption[];
  value: { server_id: string; tool_name: string };
  onChange: (value: { server_id: string; tool_name: string }) => void;
}) {
  const [query, setQuery] = useState("");
  const [activeIndex, setActiveIndex] = useState(0);
  const [open, setOpen] = useState(true);
  const options = useMemo(() => mcpToolOptions(servers), [servers]);
  const filtered = useMemo(
    () => filterMcpToolOptions(options, query),
    [options, query],
  );
  const selected = options.find(
    (option) =>
      option.serverId === value.server_id && option.toolName === value.tool_name,
  );
  const groups = filtered.reduce<Map<string, typeof filtered>>((result, item) => {
    const group = result.get(item.serverId) ?? [];
    group.push(item);
    result.set(item.serverId, group);
    return result;
  }, new Map());

  function choose(index: number) {
    const option = filtered[index];
    if (!option) return;
    onChange(mcpToolConfig(option));
    setQuery("");
    setActiveIndex(0);
    setOpen(false);
  }

  function handleKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      setOpen(true);
      setActiveIndex((current) => nextMcpToolIndex(current, event.key, filtered.length));
    } else if (event.key === "Enter" && open) {
      event.preventDefault();
      choose(activeIndex);
    } else if (event.key === "Escape") {
      setOpen(false);
    }
  }

  if (!options.length) {
    return (
      <div className="mcp-tool-picker-empty">
        <p>No approved MCP tools are available.</p>
        <Link href={`/w/${workspaceId}/integrations`} className="text-link">
          Connect an approved MCP service
        </Link>
      </div>
    );
  }

  return (
    <div className="mcp-tool-picker">
      <label htmlFor="mcp-tool-search">Approved MCP tool</label>
      <input
        id="mcp-tool-search"
        type="search"
        role="combobox"
        aria-label="Search approved MCP tools"
        aria-autocomplete="list"
        aria-expanded={open}
        aria-controls="mcp-tool-options"
        aria-activedescendant={open && filtered.length ? `mcp-tool-option-${activeIndex}` : undefined}
        placeholder="Search by server, tool, or description"
        value={query}
        onFocus={() => setOpen(true)}
        onChange={(event) => {
          setQuery(event.target.value);
          setActiveIndex(0);
          setOpen(true);
        }}
        onKeyDown={handleKeyDown}
      />
      {selected ? (
        <div className="mcp-tool-picker-selected" aria-live="polite">
          <span>
            <strong>{selected.serverName} · {selected.toolName}</strong>
            <small>
              {selected.readOnly === null
                ? "Permission details unavailable"
                : selected.readOnly
                  ? "Read only"
                  : "Can write"}
            </small>
            {selected.description && <small>{selected.description}</small>}
          </span>
          <button
            type="button"
            className="text-link"
            onClick={() => onChange({ server_id: "", tool_name: "" })}
          >
            Clear selection
          </button>
        </div>
      ) : (
        <p className="mcp-tool-picker-selected muted">No tool selected</p>
      )}
      {open && (
        <div id="mcp-tool-options" role="listbox" aria-label="Allowed MCP tools">
          {groups.size ? (
            [...groups.entries()].map(([serverId, items]) => (
              <div key={serverId} role="group" aria-label={items[0].serverName}>
                <strong className="mcp-tool-picker-group">{items[0].serverName}</strong>
                {items.map((option) => {
                  const index = filtered.indexOf(option);
                  const isSelected =
                    option.serverId === value.server_id &&
                    option.toolName === value.tool_name;
                  return (
                    <div
                      key={`${option.serverId}:${option.toolName}`}
                      id={`mcp-tool-option-${index}`}
                      role="option"
                      aria-selected={isSelected}
                      tabIndex={-1}
                      data-active={activeIndex === index}
                      className="mcp-tool-picker-option"
                      onMouseDown={(event) => event.preventDefault()}
                      onClick={() => choose(index)}
                      onKeyDown={(event) => {
                        if (event.key === "Enter" || event.key === " ") {
                          event.preventDefault();
                          choose(index);
                        }
                      }}
                    >
                      <span>{option.toolName}</span>
                      <small>
                        {option.readOnly === null
                          ? "Permission details unavailable"
                          : option.readOnly
                            ? "Read only"
                            : "Can write"}
                      </small>
                      {option.description && <small>{option.description}</small>}
                    </div>
                  );
                })}
              </div>
            ))
          ) : (
            <p className="mcp-tool-picker-empty-result" role="status">
              No allowed tools match this search.
            </p>
          )}
        </div>
      )}
    </div>
  );
}
