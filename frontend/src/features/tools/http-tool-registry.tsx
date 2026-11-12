"use client";

import { useState } from "react";
import Link from "next/link";
import { Globe, KeyRound, Plus, ShieldCheck } from "lucide-react";
import { Badge, ErrorNotice } from "@/components/shared/ui";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api/client";
import type { components } from "@/lib/api/generated";
import { connectorPreset, type ConnectorRecipe } from "./connector-presets";

export type HttpTool = components["schemas"]["HttpToolRead"];
const objectSchema = '{"type":"object"}';

function objectJson(text: string, label: string): Record<string, unknown> {
  let value: unknown;
  try {
    value = JSON.parse(text);
  } catch {
    throw new Error(`${label} must contain valid JSON.`);
  }
  if (!value || typeof value !== "object" || Array.isArray(value))
    throw new Error(`${label} must be a JSON object.`);
  return value as Record<string, unknown>;
}

export function HttpToolRegistry({
  workspaceId,
  initialTools,
  canManage,
  canTest,
}: {
  workspaceId: string;
  initialTools: HttpTool[];
  canManage: boolean;
  canTest: boolean;
}) {
  const [tools, setTools] = useState(initialTools),
    [selected, setSelected] = useState(initialTools[0]?.id ?? "");
  const [adding, setAdding] = useState(false),
    [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  const [recipe, setRecipe] = useState<ConnectorRecipe | "custom">("custom");
  const [repositoryOwner, setRepositoryOwner] = useState(""),
    [repositoryName, setRepositoryName] = useState(""),
    [channel, setChannel] = useState("");
  const [recipeHelp, setRecipeHelp] = useState<{
    instructions: string;
    docs: string;
    sample: unknown;
  } | null>(null);
  const [name, setName] = useState(""),
    [url, setUrl] = useState(""),
    [description, setDescription] = useState("");
  const [method, setMethod] = useState<HttpTool["method"]>("GET"),
    [readOnly, setReadOnly] = useState(false);
  const [authMode, setAuthMode] = useState<HttpTool["auth_mode"]>("none"),
    [authHeader, setAuthHeader] = useState("X-API-Key"),
    [credential, setCredential] = useState("");
  const [inputSchema, setInputSchema] = useState(objectSchema),
    [outputSchema, setOutputSchema] = useState(objectSchema),
    [approved, setApproved] = useState(false);
  const [input, setInput] = useState("{}"),
    [output, setOutput] = useState(""),
    [confirmed, setConfirmed] = useState(false),
    [rotation, setRotation] = useState("");
  const tool = tools.find((item) => item.id === selected),
    base = `/workspaces/${workspaceId}/http-tools`;
  function choose(id: string) {
    setSelected(id);
    setAdding(false);
    setError("");
    setOutput("");
    setRotation("");
    setConfirmed(false);
    setInput("{}");
    setCredential("");
  }
  function replace(value: HttpTool) {
    setTools((items) =>
      items.map((item) => (item.id === value.id ? value : item)),
    );
    setOutput("");
    setConfirmed(false);
  }
  function applyRecipe() {
    if (recipe === "custom") return;
    setError("");
    try {
      const preset = connectorPreset(
        recipe,
        repositoryOwner.trim(),
        repositoryName.trim(),
        channel.trim(),
      );
      setName(preset.name);
      setDescription(preset.description);
      setUrl(preset.url);
      setMethod(preset.method);
      setReadOnly(false);
      setAuthMode("bearer");
      setCredential("");
      setApproved(false);
      setInputSchema(JSON.stringify(preset.inputSchema, null, 2));
      setOutputSchema(JSON.stringify(preset.outputSchema, null, 2));
      setRecipeHelp({
        instructions: preset.instructions,
        docs: preset.docs,
        sample: preset.sample,
      });
    } catch (cause) {
      setError(
        cause instanceof Error
          ? cause.message
          : "Check the connector settings.",
      );
    }
  }
  async function create() {
    setBusy(true);
    setError("");
    try {
      let endpoint: URL;
      try {
        endpoint = new URL(url);
      } catch {
        throw new Error("Use a public HTTPS endpoint on port 443.");
      }
      if (
        endpoint.protocol !== "https:" ||
        (endpoint.port && endpoint.port !== "443")
      )
        throw new Error("Use a public HTTPS endpoint on port 443.");
      const value = await api<HttpTool>(base, {
        method: "POST",
        body: JSON.stringify({
          name,
          description,
          url,
          method,
          read_only: method === "GET" && readOnly,
          auth_mode: authMode,
          auth_header: authHeader,
          credential: authMode === "none" ? null : credential,
          input_schema: objectJson(inputSchema, "Input schema"),
          output_schema: objectJson(outputSchema, "Output schema"),
          confirm_permissions: approved,
        }),
      });
      setTools((items) => [value, ...items]);
      choose(value.id);
      setName("");
      setDescription("");
      setUrl("");
      setApproved(false);
      setReadOnly(false);
    } catch (cause) {
      setError(
        cause instanceof Error
          ? cause.message
          : "Could not approve this API tool.",
      );
    } finally {
      setBusy(false);
      setCredential("");
    }
  }
  async function update(action: "rotate" | "revoke") {
    if (!tool) return;
    setBusy(true);
    setError("");
    try {
      replace(
        await api<HttpTool>(`${base}/${tool.id}/${action}`, {
          method: "POST",
          body: JSON.stringify({
            expected_generation: tool.generation,
            ...(action === "rotate"
              ? { credential: tool.auth_mode === "none" ? null : rotation }
              : {}),
          }),
        }),
      );
    } catch (cause) {
      setError(
        cause instanceof Error
          ? cause.message
          : "Could not update this tool. Refresh and try again.",
      );
    } finally {
      setBusy(false);
      setRotation("");
    }
  }
  async function test() {
    if (!tool) return;
    setBusy(true);
    setError("");
    setOutput("");
    try {
      const result = await api<{ output: unknown }>(`${base}/${tool.id}/test`, {
        method: "POST",
        body: JSON.stringify({
          input: objectJson(input, "Input"),
          confirm_external: confirmed,
        }),
      });
      setOutput(JSON.stringify(result.output, null, 2));
    } catch (cause) {
      setError(
        cause instanceof Error
          ? cause.message
          : "Could not test this endpoint.",
      );
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="http-registry" aria-label="HTTP API tools">
      <div className="row between">
        <div>
          <span className="integration-eyebrow">CONNECT YOUR SERVICES</span>
          <h2>HTTP API tools</h2>
          <p>
            Approve a fixed API endpoint, then use it in your agents and
            workflows.
          </p>
        </div>
        {canManage && (
          <Button
            disabled={busy}
            onClick={() => {
              setAdding(true);
              setError("");
              setCredential("");
            }}
          >
            <Plus size={15} />
            Add API tool
          </Button>
        )}
      </div>
      {error && <ErrorNotice message={error} />}
      <div className="tool-registry-layout">
        <section
          className="panel tool-registry-list"
          aria-label="Approved API destinations"
        >
          <div className="tool-section-heading">
            <h3>API destinations</h3>
            <Badge tone="purple">
              {tools.filter((item) => item.state === "active").length} active
            </Badge>
          </div>
          {!tools.length && (
            <p className="http-empty">
              No API tools yet. An admin can approve a public HTTPS endpoint and
              its input contract.
            </p>
          )}
          {tools.map((item) => (
            <button
              key={item.id}
              type="button"
              disabled={busy}
              className={`tool-row ${!adding && selected === item.id ? "selected" : ""}`}
              onClick={() => choose(item.id)}
            >
              <span className="node-icon blue">
                <Globe size={18} />
              </span>
              <span>
                <strong>{item.name}</strong>
                <small>
                  {item.method} · {new URL(item.url).hostname}
                </small>
              </span>
              <Badge tone={item.state === "active" ? "green" : "neutral"}>
                {item.state === "active"
                  ? item.read_only
                    ? "Read"
                    : "Action"
                  : "Revoked"}
              </Badge>
            </button>
          ))}
        </section>
        {adding ? (
          <form
            className="panel http-tool-form"
            aria-busy={busy}
            onSubmit={(event) => {
              event.preventDefault();
              void create();
            }}
          >
            <div className="row between">
              <h3>Approve an API tool</h3>
              <Button
                type="button"
                variant="ghost"
                disabled={busy}
                onClick={() => {
                  setAdding(false);
                  setCredential("");
                }}
              >
                Cancel
              </Button>
            </div>
            <p className="node-form-hint">
              1. Service / 2. Details / 3. Approve / 4. Test / 5. Workflow
            </p>
            <section
              className="connector-setup"
              aria-label="Guided connector setup"
            >
              <label>
                Start with a service
                <select
                  value={recipe}
                  onChange={(e) => {
                    setRecipe(e.target.value as ConnectorRecipe | "custom");
                    setRecipeHelp(null);
                  }}
                >
                  <option value="custom">Custom HTTP API</option>
                  <option value="github-read">
                    GitHub · List repository issues
                  </option>
                  <option value="github-issue">
                    GitHub · Create repository issue
                  </option>
                  <option value="slack-message">
                    Slack · Send channel message
                  </option>
                </select>
              </label>
              {recipe !== "custom" && (
                <>
                  {recipe === "slack-message" ? (
                    <label>
                      Slack channel ID
                      <input
                        value={channel}
                        onChange={(e) => setChannel(e.target.value)}
                        placeholder="C0123456789"
                      />
                    </label>
                  ) : (
                    <div className="http-endpoint">
                      <label>
                        GitHub owner
                        <input
                          value={repositoryOwner}
                          onChange={(e) => setRepositoryOwner(e.target.value)}
                          placeholder="your-organization"
                        />
                      </label>
                      <label>
                        Repository
                        <input
                          value={repositoryName}
                          onChange={(e) => setRepositoryName(e.target.value)}
                          placeholder="customer-operations"
                        />
                      </label>
                    </div>
                  )}
                  <Button
                    type="button"
                    variant="outline"
                    disabled={busy}
                    onClick={applyRecipe}
                  >
                    Fill permission form
                  </Button>
                  <p className="node-form-hint">
                    This fills the form below. Review the destination and
                    contracts, enter your token and approve access. No service
                    request is sent during setup.
                  </p>
                </>
              )}
              {recipeHelp && (
                <div className="connector-guidance">
                  <p>{recipeHelp.instructions}</p>
                  <a href={recipeHelp.docs} target="_blank" rel="noreferrer">
                    Service documentation
                  </a>
                  <details>
                    <summary>Sample workflow input</summary>
                    <pre>{JSON.stringify(recipeHelp.sample, null, 2)}</pre>
                  </details>
                </div>
              )}
            </section>
            <label>
              Tool name
              <input
                required
                maxLength={100}
                value={name}
                onChange={(event) => setName(event.target.value)}
                placeholder="Look up a customer"
              />
            </label>
            <div className="http-endpoint">
              <label>
                Method
                <select
                  value={method}
                  onChange={(event) => {
                    setMethod(event.target.value as HttpTool["method"]);
                    setReadOnly(false);
                  }}
                >
                  {["GET", "POST", "PUT", "PATCH", "DELETE"].map((item) => (
                    <option key={item}>{item}</option>
                  ))}
                </select>
              </label>
              <label>
                Fixed HTTPS endpoint
                <input
                  required
                  type="url"
                  value={url}
                  onChange={(event) => setUrl(event.target.value)}
                  placeholder="https://api.example.com/customers"
                />
              </label>
            </div>
            <p className="node-form-hint">
              Public HTTPS on port 443. GET input becomes query fields; other
              methods send a JSON body. Redirects and private networks are
              blocked.
            </p>
            <label>
              Description
              <textarea
                maxLength={500}
                rows={2}
                value={description}
                onChange={(event) => setDescription(event.target.value)}
                placeholder="Explain what this API does and when it should be used."
              />
            </label>
            <label>
              Authentication
              <select
                value={authMode}
                onChange={(event) => {
                  setAuthMode(event.target.value as HttpTool["auth_mode"]);
                  setCredential("");
                }}
              >
                <option value="none">No authentication</option>
                <option value="bearer">Bearer token</option>
                <option value="api_key">API key header</option>
              </select>
            </label>
            {authMode === "api_key" && (
              <label>
                API key header
                <input
                  required
                  value={authHeader}
                  onChange={(event) => setAuthHeader(event.target.value)}
                  placeholder="X-API-Key"
                />
              </label>
            )}
            {authMode !== "none" && (
              <label>
                Credential
                <input
                  required
                  type="password"
                  autoComplete="new-password"
                  minLength={8}
                  value={credential}
                  onChange={(event) => setCredential(event.target.value)}
                  placeholder="Stored encrypted; never shown again"
                />
              </label>
            )}
            <details>
              <summary>Input and output contracts</summary>
              <p className="node-form-hint">
                Use JSON Schema to require fields. Responses are wrapped as{" "}
                {"{status_code, body}"}. Contract changes require a new tool.
              </p>
              <label>
                Input JSON Schema
                <textarea
                  className="json-editor"
                  rows={6}
                  value={inputSchema}
                  onChange={(event) => setInputSchema(event.target.value)}
                  spellCheck={false}
                />
              </label>
              <label>
                Output JSON Schema
                <textarea
                  className="json-editor"
                  rows={6}
                  value={outputSchema}
                  onChange={(event) => setOutputSchema(event.target.value)}
                  spellCheck={false}
                />
              </label>
            </details>
            {method === "GET" && (
              <label className="http-check">
                <input
                  type="checkbox"
                  checked={readOnly}
                  onChange={(event) => setReadOnly(event.target.checked)}
                />
                I reviewed this GET endpoint and it only reads data. Allow agent
                grants.
              </label>
            )}
            <label className="http-check">
              <input
                type="checkbox"
                checked={approved}
                onChange={(event) => setApproved(event.target.checked)}
              />
              I approve this destination, method and access for this workspace.
            </label>
            <p className="node-form-hint">
              Approval does not verify API credentials. Service charges are
              separate from model budgets.
            </p>
            <Button type="submit" disabled={busy || !approved}>
              <ShieldCheck size={15} />
              {busy ? "Saving…" : "Approve tool"}
            </Button>
          </form>
        ) : tool ? (
          <section className="panel http-tool-form" aria-busy={busy}>
            <div className="row between">
              <h3>{tool.name}</h3>
              <Badge tone={tool.state === "active" ? "green" : "neutral"}>
                {tool.state}
              </Badge>
            </div>
            <code className="http-url">
              {tool.method} {tool.url}
            </code>
            <p>{tool.description || "An approved workspace API endpoint."}</p>
            <div className="tool-security-note">
              <ShieldCheck size={18} />
              <span>
                {tool.read_only
                  ? "Available for read-only agent grants and workflow steps."
                  : "Available as a workflow action. Publish a workflow to execute and retain its receipt."}{" "}
                Generation {tool.generation} ·{" "}
                {tool.credential_present
                  ? "Encrypted credential"
                  : "No credential stored"}
                .
              </span>
            </div>
            {canManage && (
              <details>
                <summary>
                  <KeyRound size={13} /> Credential and access
                </summary>
                <p className="node-form-hint">
                  Replacing a credential or restoring access invalidates
                  existing published grants. Review and republish dependent
                  agents and workflows.
                </p>
                {tool.auth_mode !== "none" && (
                  <label>
                    New credential
                    <input
                      type="password"
                      autoComplete="new-password"
                      value={rotation}
                      onChange={(event) => setRotation(event.target.value)}
                    />
                  </label>
                )}
                <div className="tool-actions">
                  <Button
                    disabled={
                      busy || (tool.auth_mode !== "none" && rotation.length < 8)
                    }
                    variant="outline"
                    onClick={() => update("rotate")}
                  >
                    {tool.state === "revoked"
                      ? "Restore access"
                      : "Replace credential"}
                  </Button>
                  {tool.state === "active" && (
                    <Button
                      disabled={busy}
                      variant="outline"
                      onClick={() => update("revoke")}
                    >
                      Revoke access
                    </Button>
                  )}
                </div>
              </details>
            )}
            <p className="node-form-hint">
              {tool.state === "active"
                ? "Workspace access is approved."
                : "Workspace access is revoked."}{" "}
              Credentials are only checked when the service receives a request.
            </p>
            <Link className="text-link" href={`/w/${workspaceId}/workflows`}>
              Continue to workflows
            </Link>
            <details>
              <summary>Approved contracts</summary>
              <h4>Input</h4>
              <pre className="tool-output">
                {JSON.stringify(tool.input_schema, null, 2)}
              </pre>
              <h4>Output</h4>
              <pre className="tool-output">
                {JSON.stringify(tool.output_schema, null, 2)}
              </pre>
            </details>
            {tool.read_only && tool.method === "GET" ? (
              <div className="tool-test">
                <h3>Test endpoint</h3>
                <label>
                  Input JSON
                  <textarea
                    className="run-input"
                    value={input}
                    onChange={(event) => setInput(event.target.value)}
                    spellCheck={false}
                  />
                </label>
                <label className="http-check">
                  <input
                    type="checkbox"
                    checked={confirmed}
                    onChange={(event) => setConfirmed(event.target.checked)}
                  />
                  Send this input to {new URL(tool.url).hostname}.
                </label>
                <Button
                  disabled={
                    busy || !confirmed || !canTest || tool.state !== "active"
                  }
                  onClick={test}
                >
                  {busy ? "Testing…" : "Run external test"}
                </Button>
                <p className="node-form-hint">
                  Test output appears here only. The target service may charge
                  for requests.
                </p>
                {output && <pre className="tool-output">{output}</pre>}
              </div>
            ) : (
              <Link className="text-link" href={`/w/${workspaceId}/workflows`}>
                Create a workflow with an HTTP API node →
              </Link>
            )}
          </section>
        ) : (
          <div className="panel http-empty">
            <Globe size={28} />
            <h3>Connect a service</h3>
            <p>
              Start with a JSON API your team uses. Admins control the
              destination and credentials; builders choose approved tools.
            </p>
          </div>
        )}
      </div>
    </section>
  );
}
