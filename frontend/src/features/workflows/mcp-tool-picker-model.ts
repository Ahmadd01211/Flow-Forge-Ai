import type { McpServerOption } from "@/features/agents/model-tools";

export type McpToolOption = {
  serverId: string;
  serverName: string;
  toolName: string;
  description?: string;
  readOnly: boolean;
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
        readOnly: metadata?.read_only ?? false,
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
