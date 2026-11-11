"use client";

import { useEffect, useMemo, useRef, useState, type KeyboardEvent } from "react";
import Link from "next/link";
import type { McpServerOption } from "@/features/agents/model-tools";
import {
  filterMcpToolOptions,
  mcpToolActiveDescendant,
  mcpToolConfig,
  mcpToolOptions,
  nextMcpToolIndex,
  scrollMcpToolIntoView,
} from "./mcp-tool-picker-model";
import type { McpToolOption } from "./mcp-tool-picker-model";

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
  const [activeIndex, setActiveIndex] = useState(-1);
  const [open, setOpen] = useState(true);
  const listboxRef = useRef<HTMLDivElement>(null);
  const searchRef = useRef<HTMLInputElement>(null);
  const options = useMemo(() => mcpToolOptions(servers), [servers]);
  const filtered = useMemo(
    () => filterMcpToolOptions(options, query),
    [options, query],
  );
  const selected = options.find(
    (option) =>
      option.serverId === value.server_id && option.toolName === value.tool_name,
  );

  useEffect(() => {
    if (open) scrollMcpToolIntoView(listboxRef.current, activeIndex, filtered.length);
  }, [activeIndex, filtered.length, open]);

  function choose(index: number) {
    const option = filtered[index];
    if (!option) return;
    onChange(mcpToolConfig(option));
    setQuery("");
    setActiveIndex(-1);
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
        aria-activedescendant={mcpToolActiveDescendant(open, activeIndex, filtered.length)}
        placeholder="Search by server, tool, or description"
        value={query}
        ref={searchRef}
        onFocus={() => setOpen(true)}
        onClick={() => setOpen(true)}
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
            onClick={() => {
              onChange({ server_id: "", tool_name: "" });
              setActiveIndex(-1);
              setOpen(true);
              searchRef.current?.focus();
            }}
          >
            Clear selection
          </button>
        </div>
      ) : (
        <p className="mcp-tool-picker-selected muted">No tool selected</p>
      )}
      {open && (
        <div ref={listboxRef} id="mcp-tool-options" role="listbox" aria-label="Allowed MCP tools">
          <McpToolPickerResults
            options={filtered}
            activeIndex={activeIndex}
            selected={value}
            onChoose={choose}
          />
        </div>
      )}
    </div>
  );
}

export function McpToolPickerResults({
  options,
  activeIndex,
  selected,
  onChoose,
}: {
  options: McpToolOption[];
  activeIndex: number;
  selected: { server_id: string; tool_name: string };
  onChoose: (index: number) => void;
}) {
  if (!options.length) {
    return (
      <p className="mcp-tool-picker-empty-result" role="status">
        No allowed tools match this search.
      </p>
    );
  }
  const groups = options.reduce<Map<string, McpToolOption[]>>((result, item) => {
    const group = result.get(item.serverId) ?? [];
    group.push(item);
    result.set(item.serverId, group);
    return result;
  }, new Map());
  return [...groups.entries()].map(([serverId, items]) => (
    <div key={serverId} role="group" aria-label={items[0].serverName}>
      <strong className="mcp-tool-picker-group">{items[0].serverName}</strong>
      {items.map((option) => {
        const index = options.indexOf(option);
        const isSelected =
          option.serverId === selected.server_id &&
          option.toolName === selected.tool_name;
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
            onClick={() => onChoose(index)}
            onKeyDown={(event) => {
              if (event.key === "Enter" || event.key === " ") {
                event.preventDefault();
                onChoose(index);
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
  ));
}
