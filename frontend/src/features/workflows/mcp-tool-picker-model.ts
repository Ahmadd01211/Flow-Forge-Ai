import type { McpServerOption } from "@/features/agents/model-tools";

export type McpToolOption = {
  serverId: string;
  serverName: string;
  toolName: string;
  description?: string;
  readOnly: boolean | null;
  schema: unknown;
};

export function mcpToolOptions(servers: McpServerOption[]): McpToolOption[] {
  return servers.flatMap((server) =>
    server.runnable_tools.map((toolName) => {
      const metadata = server.tools?.find((tool) => tool.name === toolName);
      return {
        serverId: server.id,
        serverName: server.name,
        toolName,
        description: metadata?.description?.trim() || undefined,
        readOnly: metadata?.read_only ?? null,
        schema: server.runnable_schemas[toolName],
      };
    }),
  );
}

export function filterMcpToolOptions(
  options: McpToolOption[],
  query: string,
): McpToolOption[] {
  const normalized = query.trim().toLocaleLowerCase();
  if (!normalized) return options;
  return options.filter((option) =>
    [option.serverName, option.toolName, option.description]
      .filter(Boolean)
      .some((value) => value!.toLocaleLowerCase().includes(normalized)),
  );
}

export function nextMcpToolIndex(
  current: number,
  key: string,
  count: number,
): number {
  if (count === 0) return -1;
  if (key === "ArrowDown") return current < 0 ? 0 : (current + 1) % count;
  if (key === "ArrowUp") return current <= 0 ? count - 1 : current - 1;
  return current;
}

export function mcpToolActiveDescendant(
  open: boolean,
  activeIndex: number,
  count: number,
): string | undefined {
  return open && activeIndex >= 0 && activeIndex < count
    ? `mcp-tool-option-${activeIndex}`
    : undefined;
}

type ScrollableListbox = {
  querySelector: (
    selectors: string,
  ) => { scrollIntoView: (options: { block: "nearest" }) => void } | null;
};

export function scrollMcpToolIntoView(
  listbox: ScrollableListbox | null,
  activeIndex: number,
  count: number,
): void {
  if (!listbox || activeIndex < 0 || activeIndex >= count) return;
  listbox
    .querySelector(`#mcp-tool-option-${activeIndex}`)
    ?.scrollIntoView({ block: "nearest" });
}

export function mcpToolConfig(option: McpToolOption): {
  server_id: string;
  tool_name: string;
} {
  return { server_id: option.serverId, tool_name: option.toolName };
}
