"use client";
import Link from "next/link";
import { ShieldCheck, Sparkles } from "lucide-react";
import { LocalTime } from "@/components/shared/local-time";
import { Button } from "@/components/ui/button";
import type { AgentConfig, Connection } from "@/lib/api/types";
import type { ToolEntry } from "@/features/tools/tool-registry";
import type { HttpTool } from "@/features/tools/http-tool-registry";
import { HttpGrants } from "./http-grants";
import { isRunnableModel } from "./runnable-models";

export type ModelToolsConfig = Pick<AgentConfig, "provider" | "model_id" | "tool_keys" | "mcp_tools" | "http_tools">;
export type McpServerOption = {
  id: string;
  name: string;
  runnable_tools: string[];
  runnable_schemas: Record<string, unknown>;
  tools?: { name: string; read_only: boolean }[];
};

/** Provider, verified model and tool grants; shared by the agent editor and workflow LLM steps. */
export function ModelAndTools({
  workspaceId,
  config,
  setConfig,
  connections,
  tools,
  mcpServers,
  httpTools,
  canEdit = true,
}: {
  workspaceId: string;
  config: ModelToolsConfig;
  setConfig: (next: ModelToolsConfig) => void;
  connections: Connection[];
  tools: ToolEntry[];
  mcpServers: McpServerOption[];
  httpTools: HttpTool[];
  canEdit?: boolean;
}) {
  const connection = connections.find((item) => item.provider === config.provider);
  return (
    <>
        <label className="form-stack mt-6">
          Provider
          <select
            value={config.provider}
            onChange={(e) =>
              setConfig({
                ...config,
                provider: e.target.value as AgentConfig["provider"],
                tool_keys: [],
                mcp_tools: [],
                http_tools: [],
                model_id:
                  connections.find(
                    (item) => item.provider === e.target.value,
                  )?.default_model_id || "",
              })
            }
            disabled={!canEdit}
          >
            <option value="openai">OpenAI</option>
            <option value="openrouter">OpenRouter</option>
            <option value="anthropic">Claude (Anthropic)</option>
            <option value="gemini">Gemini (Google)</option>
            <option value="deepseek">DeepSeek</option>
          </select>
        </label>
        {connection?.state === "active" ? (
          <div className="form-stack mt-6">
            <label>
              Verified model
              <select
                value={config.model_id}
                onChange={(e) =>
                  setConfig({
                    ...config,
                    model_id: e.target.value,
                    mcp_tools: connection.model_capabilities[
                      e.target.value
                    ]?.local_tools
                      ? config.mcp_tools
                      : [],
                    tool_keys: connection.model_capabilities[
                      e.target.value
                    ]?.local_tools
                      ? config.tool_keys
                      : [],
                    http_tools: connection.model_capabilities[e.target.value]?.local_tools ? config.http_tools : [],
                  })
                }
                disabled={!canEdit}
              >
                <option value="">Choose a model</option>
                {connection.verified_models.map((id) => (
                  <option value={id} key={id}>
                    {id}
                    {isRunnableModel(connections, config.provider, id)
                      ? " · Live runs"
                      : " · Setup only"}
                  </option>
                ))}
              </select>
            </label>
            <p className="field-hint">
              Access was checked on{" "}
              <LocalTime value={connection.verified_at} />.
              Publishing validates your saved schema; it does not
              execute the model. Live runs are available only for
              models marked above.
            </p>
          </div>
        ) : (
          <div className="inline-empty">
            <Sparkles size={25} />
            <h3>No model provider connected</h3>
            <p>
              Connect a provider in Integrations before choosing a
              model or publishing.
            </p>
            <Button asChild variant="outline">
              <Link href={`/w/${workspaceId}/integrations`}>
                Open integrations
              </Link>
            </Button>
          </div>
        )}
        <div className="permission-callout">
          <ShieldCheck size={18} />
          <div>
            <strong>
              {config.tool_keys.length + config.mcp_tools.length + config.http_tools.length
                ? `${config.tool_keys.length + config.mcp_tools.length + config.http_tools.length} tool grant${config.tool_keys.length + config.mcp_tools.length + config.http_tools.length === 1 ? "" : "s"} selected`
                : "No tool access granted"}
            </strong>
            <p>
              Models with tool support can call selected tools after
              publication. Workspace approval is checked when each run
              starts and before each call.
            </p>
          </div>
        </div>
        <div className="agent-tool-list">
          {tools.map((tool) => (
            <div key={tool.key} className="agent-tool-option">
              <label className="agent-tool-selection">
                <input
                  type="checkbox"
                  aria-label={`Grant ${tool.name}`}
                  checked={config.tool_keys.includes(
                    tool.key as AgentConfig["tool_keys"][number],
                  )}
                  disabled={
                    !canEdit ||
                    !tool.installed ||
                    !connection?.model_capabilities[config.model_id]
                      ?.local_tools
                  }
                  onChange={(event) => {
                    const keys = event.target.checked
                      ? [
                          ...config.tool_keys,
                          tool.key as AgentConfig["tool_keys"][number],
                        ]
                      : config.tool_keys.filter(
                          (key) => key !== tool.key,
                        );
                    setConfig({ ...config, tool_keys: keys });
                  }}
                />
                <span>
                  <strong>{tool.name}</strong>
                  <small>
                    {tool.installed
                      ? tool.description
                      : "Approve in Tool Registry first"}
                  </small>
                </span>
              </label>
              <details className="agent-tool-contract">
                <summary>Arguments and permissions</summary>
                <p>
                  {tool.read_only
                    ? "Read-only local tool. No network or credential access."
                    : "Review this tool's permissions before granting access."}
                </p>
                <pre>
                  {JSON.stringify(tool.input_schema, null, 2)}
                </pre>
              </details>
            </div>
          ))}
          {!tools.length && (
            <p className="field-hint">
              No reviewed tools are available yet.
            </p>
          )}
          <Button asChild variant="outline" size="sm">
            <Link href={`/w/${workspaceId}/tools`}>
              Open Tool Registry
            </Link>
          </Button>
        </div>
        <section className="agent-mcp-grants">
          <h3>Connected MCP tools</h3>
          <p>
            Select allowed tools from your workspace MCP servers. Write tools act on the external service.
            Publication pins each tool schema and credential
            generation.
          </p>
          {mcpServers.flatMap((server) =>
            server.runnable_tools.map((name) => {
              const selected = config.mcp_tools.some(
                (g) =>
                  g.server_id === server.id && g.tool_name === name,
              );
              return (
                <div
                  className="agent-tool-option"
                  key={`${server.id}/${name}`}
                >
                  <label
                    className="agent-tool-selection"
                    htmlFor={`mcp-grant-${server.id}-${name}`}
                  >
                    <input
                      type="checkbox"
                      id={`mcp-grant-${server.id}-${name}`}
                      aria-label={`Grant ${server.name} / ${name}`}
                      checked={selected}
                      disabled={
                        !canEdit ||
                        (!selected &&
                          (!connection?.model_capabilities[
                            config.model_id
                          ]?.local_tools ||
                            config.mcp_tools.length >= 8))
                      }
                      onChange={(e) =>
                        setConfig({
                          ...config,
                          mcp_tools: e.target.checked
                            ? [
                                ...config.mcp_tools,
                                {
                                  server_id: server.id,
                                  tool_name: name,
                                  description: "",
                                },
                              ]
                            : config.mcp_tools.filter(
                                (g) =>
                                  g.server_id !== server.id ||
                                  g.tool_name !== name,
                              ),
                        })
                      }
                    />
                    <span>
                      <strong>
                        {server.name} / {name}
                      </strong>
                      <small>
                        {server.tools?.find((tool) => tool.name === name)
                          ?.read_only
                          ? "Read-only remote tool"
                          : "Can change data in the external service"}
                      </small>
                    </span>
                  </label>
                  <details>
                    <summary>Input schema</summary>
                    <pre>
                      {JSON.stringify(
                        server.runnable_schemas[name],
                        null,
                        2,
                      )}
                    </pre>
                  </details>
                </div>
              );
            }),
          )}
          {config.mcp_tools
            .filter(
              (g) =>
                !mcpServers.some(
                  (s) =>
                    s.id === g.server_id &&
                    s.runnable_tools.includes(g.tool_name),
                ),
            )
            .map((g) => (
              <p key={`${g.server_id}/${g.tool_name}`}>
                {g.server_id}/{g.tool_name} is no longer available.{" "}
                <button
                  disabled={!canEdit}
                  onClick={() =>
                    setConfig({
                      ...config,
                      mcp_tools: config.mcp_tools.filter(
                        (x) => x !== g,
                      ),
                    })
                  }
                >
                  Remove grant
                </button>
              </p>
            ))}
          {!mcpServers.some((s) => s.runnable_tools.length) && (
            <p>No allowed MCP tools yet. Add or connect a server in Integrations.</p>
          )}
          <Link
            className="text-link"
            href={`/w/${workspaceId}/integrations`}
          >
            Manage MCP connections
          </Link>
        </section>
        <HttpGrants workspaceId={workspaceId} tools={httpTools} grants={config.http_tools} onChange={http_tools => setConfig({ ...config, http_tools })} canEdit={canEdit} modelAllowsTools={!!connection?.model_capabilities[config.model_id]?.local_tools} />
    </>
  );
}
