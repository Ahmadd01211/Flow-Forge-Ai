"use client";
import Link from "next/link";
import type { AgentConfig } from "@/lib/api/types";
import type { HttpTool } from "@/features/tools/http-tool-registry";

export function HttpGrants({
  workspaceId,
  tools,
  grants,
  onChange,
  canEdit,
  modelAllowsTools,
}: {
  workspaceId: string;
  tools: HttpTool[];
  grants: AgentConfig["http_tools"];
  onChange: (grants: AgentConfig["http_tools"]) => void;
  canEdit: boolean;
  modelAllowsTools: boolean;
}) {
  const available = tools.filter(
    (item) =>
      item.state === "active" && item.read_only && item.method === "GET",
  );
  return (
    <section className="agent-mcp-grants">
      <h3>HTTP API tools</h3>
      <p>
        Grant access to approved read-only endpoints. Publish pins the endpoint
        contract and credential generation. Service charges are separate from
        model budgets.
      </p>
      {available.map((tool) => {
        const selected = grants.some((grant) => grant.tool_id === tool.id);
        return (
          <div className="agent-tool-option" key={tool.id}>
            <label className="agent-tool-selection" aria-label={`Grant ${tool.name}`}>
              <input
                type="checkbox"
                checked={selected}
                disabled={
                  !canEdit ||
                  (!selected && (!modelAllowsTools || grants.length >= 8))
                }
                onChange={(event) =>
                  onChange(
                    event.target.checked
                      ? [
                          ...grants,
                          {
                            tool_id: tool.id,
                            name: tool.name,
                            description: tool.description,
                          },
                        ]
                      : grants.filter((grant) => grant.tool_id !== tool.id),
                  )
                }
              />
              <span>
                <strong>{tool.name}</strong>
                <small>GET · {new URL(tool.url).hostname} · read only</small>
              </span>
            </label>
            <details>
              <summary>Input schema</summary>
              <pre>{JSON.stringify(tool.input_schema, null, 2)}</pre>
            </details>
          </div>
        );
      })}
      {grants
        .filter((grant) => !available.some((tool) => tool.id === grant.tool_id))
        .map((grant) => (
          <p key={grant.tool_id}>
            {grant.name || grant.tool_id} is unavailable.{" "}
            <button
              disabled={!canEdit}
              onClick={() => onChange(grants.filter((item) => item !== grant))}
            >
              Remove grant
            </button>
          </p>
        ))}
      {!available.length && <p>No reviewed read-only API tools yet.</p>}
      <Link className="text-link" href={`/w/${workspaceId}/tools`}>
        Manage API tools
      </Link>
    </section>
  );
}
