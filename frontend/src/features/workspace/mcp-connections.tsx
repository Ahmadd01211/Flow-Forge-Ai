"use client";

import { useState } from "react";
import Link from "next/link";
import {
  Check,
  Globe2,
  KeyRound,
  LoaderCircle,
  Plus,
  ShieldCheck,
} from "lucide-react";
import { Badge, ErrorNotice } from "@/components/shared/ui";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api/client";
import { exampleArguments, toolFields } from "@/features/workspace/mcp-schema";
import {
  DEEPWIKI_MCP_URL,
  GITHUB_TOOLSETS,
  githubMcpName,
  githubMcpUrl,
  type GithubToolset,
} from "@/features/workspace/mcp-presets";

export interface McpTool {
  name: string;
  description?: string;
  read_only_hint?: boolean;
  destructive_hint?: boolean;
  read_only: boolean;
  policy: "allow" | "block";
}

export interface McpServer {
  id: string;
  name: string;
  source: "catalog" | "workspace";
  origin: string | null;
  allowed_tools: string[];
  verified_tools: string[];
  runnable_tools: string[];
  runnable_schemas: Record<string, unknown>;
  tools: McpTool[];
  policy_editable: boolean;
  state: "not_connected" | "active" | "revoked";
  verified_at: string | null;
}

export interface McpListing {
  items: McpServer[];
  workspace_servers: boolean;
}

/** Owners/admins may test any allowed tool; others only allowed read-only tools of workspace servers. */
export function testableTools(server: McpServer, manager: boolean): string[] {
  return server.tools
    .filter((tool) =>
      server.source === "catalog"
        ? tool.policy === "allow" || !tool.read_only
        : tool.policy === "allow" && (tool.read_only || manager),
    )
    .map((tool) => tool.name);
}

function toolKind(tool: McpTool): [string, "green" | "amber" | "neutral"] {
  if (tool.destructive_hint) return ["Destructive", "amber"];
  return tool.read_only ? ["Read-only", "green"] : ["Write", "neutral"];
}

export function McpConnections({
  workspaceId,
  initial,
  canManage,
  canTest,
}: {
  workspaceId: string;
  initial: McpListing;
  canManage: boolean;
  canTest: boolean;
}) {
  const [servers, setServers] = useState(initial.items);
  const [selected, setSelected] = useState(initial.items[0]?.id || "");
  const [adding, setAdding] = useState(false);
  const [draft, setDraft] = useState({ name: "", url: "", token: "" });
  const [preset, setPreset] = useState<"" | "github">("");
  const [githubToolset, setGithubToolset] = useState<GithubToolset>("");
  const [githubReadOnly, setGithubReadOnly] = useState(true);
  const [token, setToken] = useState("");
  const [selectedTool, setSelectedTool] = useState("");
  const [argumentDrafts, setArgumentDrafts] = useState<Record<string, string>>(
    {},
  );
  const [output, setOutput] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const server = adding
    ? undefined
    : servers.find((item) => item.id === selected);
  const testable = server ? testableTools(server, canManage) : [];
  const tool = testable.includes(selectedTool)
    ? selectedTool
    : testable[0] || "";
  const fields =
    server && tool ? toolFields(server.runnable_schemas[tool]) : [];
  const argumentKey = JSON.stringify([server?.id, tool]);
  const argumentsJson =
    argumentDrafts[argumentKey] ??
    JSON.stringify(exampleArguments(server?.runnable_schemas[tool]), null, 2);
  function setArgumentsJson(value: string) {
    setArgumentDrafts((current) => ({ ...current, [argumentKey]: value }));
  }
  let argumentError = "";
  try {
    const parsed: unknown = JSON.parse(argumentsJson);
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed))
      argumentError = "Arguments must be a JSON object.";
    else {
      const missing = fields.filter(
        (field) => field.required && !Object.hasOwn(parsed, field.name),
      );
      if (missing.length)
        argumentError = `Add required inputs: ${missing.map((field) => field.name).join(", ")}.`;
    }
  } catch {
    argumentError = "Enter valid JSON with double-quoted field names.";
  }
  const base = `/workspaces/${workspaceId}/mcp`;
  const canAdd = canManage && initial.workspace_servers;

  function chooseGithub(toolset: GithubToolset, readOnly: boolean) {
    setGithubToolset(toolset);
    setGithubReadOnly(readOnly);
    setDraft((current) => ({
      ...current,
      name: githubMcpName(toolset, readOnly),
      url: githubMcpUrl(toolset, readOnly),
    }));
  }

  function choose(id: string) {
    setSelected(id);
    setAdding(false);
    setToken("");
    setSelectedTool("");
    setOutput("");
    setError("");
    setNotice("");
  }

  async function run(action: () => Promise<void>, failure: string) {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await action();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : failure);
    } finally {
      setBusy(false);
    }
  }

  const add = () =>
    run(async () => {
      const result = await api<
        McpListing & { added: string; skipped_tools: number }
      >(`${base}/servers`, {
        method: "POST",
        body: JSON.stringify({
          name: draft.name.trim(),
          url: draft.url.trim(),
          bearer_token: draft.token,
        }),
      });
      setServers(result.items);
      setDraft({ name: "", url: "", token: "" });
      setPreset("");
      setAdding(false);
      setSelected(result.added);
      setNotice(
        `Server added. Read-only tools are allowed; review each write tool before allowing it.${result.skipped_tools ? ` ${result.skipped_tools} tool(s) were skipped because their names or input schemas are not supported.` : ""}`,
      );
    }, "Could not add this MCP server.");

  const connect = () =>
    run(async () => {
      if (!server) return;
      const result = await api<McpListing>(`${base}/${server.id}`, {
        method: "PUT",
        body: JSON.stringify({ bearer_token: token }),
      });
      setServers(result.items);
      setToken("");
      setOutput("");
      setNotice(
        "Server verified. Tool policies were kept for tools that still exist.",
      );
    }, "Could not connect this MCP server.");

  const disconnect = () =>
    run(async () => {
      if (!server) return;
      const result = await api<McpListing>(`${base}/${server.id}`, {
        method: "DELETE",
      });
      setServers(result.items);
      setSelectedTool("");
      setOutput("");
      if (server.source === "workspace") setSelected(result.items[0]?.id || "");
      setNotice(
        server.source === "workspace"
          ? "Server removed with its stored URL and token. Agents and workflows using it stop before their next call."
          : "Connection revoked and its stored token removed.",
      );
    }, "Could not revoke this MCP server.");

  const setPolicy = (name: string, policy: "allow" | "block") =>
    run(async () => {
      if (!server) return;
      const result = await api<McpListing>(
        `${base}/${server.id}/tools/${encodeURIComponent(name)}`,
        { method: "PATCH", body: JSON.stringify({ policy }) },
      );
      setServers(result.items);
      setNotice(
        policy === "allow"
          ? `${name} is allowed. Agents and workflows must still be granted it explicitly.`
          : `${name} is blocked. Runs that use it stop before calling the server.`,
      );
    }, "Could not change this tool policy.");

  const test = () =>
    run(async () => {
      if (!server || !tool || argumentError) return;
      setOutput("");
      const parsed: unknown = JSON.parse(argumentsJson);
      if (!parsed || typeof parsed !== "object" || Array.isArray(parsed))
        throw new Error("Arguments must be a JSON object.");
      const result = await api<{ output: unknown }>(
        `${base}/${server.id}/tools/${encodeURIComponent(tool)}/test`,
        { method: "POST", body: JSON.stringify({ arguments: parsed }) },
      );
      setOutput(JSON.stringify(result.output, null, 2));
    }, "MCP tool test failed.");

  const addForm = (
    <div className="mcp-detail">
      <h3>Add an MCP server</h3>
      <p className="node-form-hint">
        1. Service / 2. Details / 3. Verify / 4. Test / 5. Workflow
      </p>
      <details>
        <summary>Connection help</summary>
        <p>
          Use a public HTTPS Streamable HTTP endpoint. Tokens are stored
          encrypted. OAuth sign-in is not supported; use a token or a public
          server.
        </p>
        <p>
          Read-only tools start allowed. Review write tools before enabling
          them.
        </p>
      </details>
      {error && <ErrorNotice message={error} />}
      <div className="mcp-credential">
        <span className="integration-eyebrow">QUICK SETUP</span>
        <div className="row">
          <button
            type="button"
            className="chip-button"
            disabled={busy}
            onClick={() => {
              setPreset("github");
              setDraft({
                ...draft,
                name: githubMcpName(githubToolset, githubReadOnly),
                url: githubMcpUrl(githubToolset, githubReadOnly),
              });
            }}
          >
            GitHub
          </button>
          <button
            type="button"
            className="chip-button"
            disabled={busy}
            onClick={() => {
              setPreset("");
              setDraft({ name: "DeepWiki", url: DEEPWIKI_MCP_URL, token: "" });
            }}
          >
            DeepWiki (public, no token)
          </button>
        </div>
        {preset === "github" && (
          <>
            <label htmlFor="mcp-github-toolset">GitHub toolset</label>
            <select
              id="mcp-github-toolset"
              value={githubToolset}
              disabled={busy}
              onChange={(event) =>
                chooseGithub(
                  event.target.value as GithubToolset,
                  githubReadOnly,
                )
              }
            >
              {GITHUB_TOOLSETS.map(([key, label]) => (
                <option key={key} value={key}>
                  {label}
                </option>
              ))}
            </select>
            <label>
              <input
                type="checkbox"
                checked={githubReadOnly}
                disabled={busy}
                onChange={(event) =>
                  chooseGithub(githubToolset, event.target.checked)
                }
              />{" "}
              Read-only tools only (recommended to start)
            </label>
            <details>
              <summary>Get a GitHub token</summary>
              <p>
                Create a{" "}
                <a
                  className="text-link"
                  href="https://github.com/settings/personal-access-tokens/new"
                  target="_blank"
                  rel="noreferrer"
                >
                  fine-grained personal access token
                </a>{" "}
                limited to the repositories this workspace needs, with only the
                permissions you plan to allow, for example Issues: read, or
                Issues: read and write. Paste it below; it is stored encrypted.
              </p>
            </details>
          </>
        )}
        <label htmlFor="mcp-name">Name</label>
        <input
          id="mcp-name"
          value={draft.name}
          maxLength={100}
          disabled={busy}
          onChange={(event) => setDraft({ ...draft, name: event.target.value })}
          placeholder="Issue tracker"
        />
        <label htmlFor="mcp-url">
          Server URL{" "}
          <small>Stored encrypted: some services put a key in the URL</small>
        </label>
        <input
          id="mcp-url"
          type="url"
          value={draft.url}
          maxLength={2048}
          disabled={busy}
          spellCheck={false}
          autoComplete="off"
          onChange={(event) => setDraft({ ...draft, url: event.target.value })}
          placeholder="https://mcp.example.com/mcp"
        />
        <label htmlFor="mcp-new-token">
          {preset === "github"
            ? "GitHub personal access token"
            : "Bearer token"}{" "}
          <small>
            {preset === "github"
              ? "Required"
              : "Leave blank for a public server"}
          </small>
        </label>
        <div className="integration-key-row">
          <div className="integration-key-input">
            <KeyRound size={16} />
            <input
              id="mcp-new-token"
              type="password"
              autoComplete="off"
              value={draft.token}
              disabled={busy}
              onChange={(event) =>
                setDraft({ ...draft, token: event.target.value })
              }
              placeholder="Optional server token"
            />
          </div>
          <Button
            disabled={busy || !draft.name.trim() || !draft.url.trim()}
            onClick={add}
          >
            {busy ? (
              <LoaderCircle size={15} className="spin" />
            ) : (
              <ShieldCheck size={15} />
            )}
            Add and verify
          </Button>
        </div>
      </div>
    </div>
  );

  return (
    <section className="panel mcp-panel">
      <div className="mcp-heading">
        <div>
          <span className="integration-eyebrow">REMOTE CAPABILITIES</span>
          <h2>MCP servers</h2>
          <p>Connect tools for your agents and workflows.</p>
        </div>
        <div className="row">
          <Badge tone="purple">
            {servers.filter((item) => item.state === "active").length} connected
          </Badge>
          {canAdd && (
            <Button
              variant="outline"
              disabled={busy}
              onClick={() => {
                setAdding(true);
                setError("");
                setNotice("");
              }}
            >
              <Plus size={14} />
              Add server
            </Button>
          )}
        </div>
      </div>
      {!servers.length && !adding ? (
        <div className="mcp-empty">
          <Globe2 size={24} />
          <div>
            <strong>No MCP servers yet</strong>
            <p>
              {canAdd
                ? "Add a server with Add server above."
                : initial.workspace_servers
                  ? "An owner or admin can add a server."
                  : "This installation only permits servers reviewed by a platform operator."}
            </p>
          </div>
        </div>
      ) : (
        <div className="mcp-layout">
          <div className="mcp-server-list">
            {servers.map((item) => (
              <button
                type="button"
                key={item.id}
                className={!adding && selected === item.id ? "selected" : ""}
                onClick={() => choose(item.id)}
              >
                <Globe2 size={18} />
                <span>
                  <strong>{item.name}</strong>
                  <small>
                    {item.state === "active"
                      ? `${item.runnable_tools.length} of ${item.verified_tools.length} tools allowed`
                      : "Not connected"}
                    {item.source === "workspace"
                      ? " · added by workspace"
                      : " · operator reviewed"}
                  </small>
                </span>
                <Badge tone={item.state === "active" ? "green" : "amber"}>
                  {item.state === "active" ? "Connected" : "Available"}
                </Badge>
              </button>
            ))}
          </div>
          {adding
            ? addForm
            : server && (
                <div className="mcp-detail">
                  <div className="row between">
                    <h3>{server.name}</h3>
                    <Badge tone={server.state === "active" ? "green" : "amber"}>
                      {server.state === "active"
                        ? "Verified"
                        : "Awaiting connection"}
                    </Badge>
                  </div>
                  <details>
                    <summary>Server details</summary>
                    <p>
                      {server.source === "workspace"
                        ? `Added by this workspace · ${server.origin}`
                        : "Reviewed by a platform operator"}
                      . Remote descriptions and labels come from the server and
                      do not grant permissions by themselves.
                    </p>{" "}
                  </details>

                  {error && <ErrorNotice message={error} />}
                  {notice && (
                    <div className="integration-notice">
                      <Check size={16} /> {notice}
                    </div>
                  )}
                  {server.state === "active" && (
                    <details className="mcp-test">
                      <summary>
                        Tool permissions ({server.tools.length})
                      </summary>
                      {server.tools.map((item) => {
                        const [kind, tone] = toolKind(item);
                        return (
                          <div className="row between" key={item.name}>
                            <div>
                              <strong>{item.name}</strong>{" "}
                              <Badge tone={tone}>{kind}</Badge>
                              {item.description && <p>{item.description}</p>}
                            </div>
                            {canManage && server.policy_editable ? (
                              <select
                                aria-label={`Policy for ${item.name}`}
                                value={item.policy}
                                disabled={busy}
                                onChange={(event) =>
                                  setPolicy(
                                    item.name,
                                    event.target.value as "allow" | "block",
                                  )
                                }
                              >
                                <option value="allow">Allow</option>
                                <option value="block">Block</option>
                              </select>
                            ) : (
                              <Badge
                                tone={
                                  item.policy === "allow" ? "green" : "neutral"
                                }
                              >
                                {item.policy === "allow"
                                  ? "Allowed"
                                  : "Blocked"}
                              </Badge>
                            )}
                          </div>
                        );
                      })}
                      {canManage && server.policy_editable && (
                        <p>
                          Allowing a write tool lets granted agents and
                          published workflows act on the external service. Put a
                          Human approval step before it in a workflow when a
                          person should review each action.
                        </p>
                      )}
                    </details>
                  )}
                  {canManage && (
                    <details
                      className="mcp-credential"
                      open={server.state !== "active"}
                    >
                      <summary>
                        {server.state === "active"
                          ? "Credentials and access"
                          : "Connect server"}
                      </summary>
                      <label htmlFor="mcp-token">
                        Bearer token{" "}
                        <small>Leave blank for a public server</small>
                      </label>
                      <div className="integration-key-row">
                        <div className="integration-key-input">
                          <KeyRound size={16} />
                          <input
                            id="mcp-token"
                            type="password"
                            autoComplete="off"
                            value={token}
                            onChange={(event) => setToken(event.target.value)}
                            placeholder="Optional server token"
                          />
                        </div>
                        <Button disabled={busy} onClick={connect}>
                          {busy ? (
                            <LoaderCircle size={15} className="spin" />
                          ) : (
                            <ShieldCheck size={15} />
                          )}
                          {server.state === "active"
                            ? "Verify or rotate"
                            : "Connect server"}
                        </Button>
                      </div>
                      {server.state === "active" && (
                        <button
                          className="mcp-revoke"
                          type="button"
                          disabled={busy}
                          onClick={disconnect}
                        >
                          {server.source === "workspace"
                            ? "Remove server"
                            : "Revoke connection"}
                        </button>
                      )}
                    </details>
                  )}
                  {server.state === "active" && (
                    <div className="mcp-test">
                      <h4>Test a tool</h4>
                      {testable.length ? (
                        <>
                          <label htmlFor="mcp-tool">Tool</label>
                          <select
                            id="mcp-tool"
                            value={tool}
                            onChange={(event) => {
                              setSelectedTool(event.target.value);
                              setOutput("");
                            }}
                          >
                            {testable.map((name) => (
                              <option key={name} value={name}>
                                {name}
                              </option>
                            ))}
                          </select>
                          {fields.length > 0 && (
                            <details>
                              <summary>Inputs for {tool}</summary>
                              <ul className="mcp-fields">
                                {fields.map((field) => (
                                  <li key={field.name}>
                                    <code>{field.name}</code>{" "}
                                    <small>
                                      {field.type}
                                      {field.required
                                        ? " · required"
                                        : " · optional"}
                                    </small>
                                    {field.description && (
                                      <p>{field.description}</p>
                                    )}
                                  </li>
                                ))}
                              </ul>
                            </details>
                          )}
                          <div className="row between">
                            <label htmlFor="mcp-arguments">
                              Arguments JSON
                            </label>
                            {fields.length > 0 && (
                              <button
                                type="button"
                                className="chip-button"
                                onClick={() =>
                                  setArgumentsJson(
                                    JSON.stringify(
                                      exampleArguments(
                                        server.runnable_schemas[tool],
                                      ),
                                      null,
                                      2,
                                    ),
                                  )
                                }
                              >
                                Fill required fields
                              </button>
                            )}
                          </div>
                          <p className="node-form-hint">
                            Replace example values before testing.
                          </p>
                          <textarea
                            id="mcp-arguments"
                            aria-invalid={Boolean(argumentError)}
                            aria-describedby={
                              argumentError ? "mcp-arguments-error" : undefined
                            }
                            className="run-input"
                            spellCheck={false}
                            value={argumentsJson}
                            onChange={(event) =>
                              setArgumentsJson(event.target.value)
                            }
                          />
                          {argumentError && (
                            <p id="mcp-arguments-error" role="status">
                              {argumentError}
                            </p>
                          )}
                          {server.tools.find((item) => item.name === tool)
                            ?.read_only === false && (
                            <p>
                              This tool is not marked read-only. A test makes a
                              real call that may change data.
                            </p>
                          )}
                          <Button
                            disabled={
                              busy ||
                              !canTest ||
                              !tool ||
                              Boolean(argumentError)
                            }
                            onClick={test}
                          >
                            Run tool test
                          </Button>
                          {output && (
                            <>
                              <label htmlFor="mcp-output">Response JSON</label>
                              <pre id="mcp-output" className="tool-output">
                                {output}
                              </pre>
                            </>
                          )}
                        </>
                      ) : (
                        <p>
                          No allowed tools you can test. Write tools run from
                          agents or published workflows.
                        </p>
                      )}
                    </div>
                  )}
                  <Link
                    className="text-link"
                    href={`/w/${workspaceId}/workflows`}
                  >
                    Continue to workflows
                  </Link>
                </div>
              )}
        </div>
      )}
    </section>
  );
}
