"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import {
  Check,
  ChevronRight,
  KeyRound,
  LoaderCircle,
  LockKeyhole,
  Search,
  ShieldCheck,
  Trash2,
} from "lucide-react";
import { Badge, ErrorNotice, PageHeader } from "@/components/shared/ui";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api/client";
import type { Connection } from "@/lib/api/types";

const providers: { id: Connection["provider"]; name: string }[] = [
  { id: "openai", name: "OpenAI" },
  { id: "openrouter", name: "OpenRouter" },
  { id: "anthropic", name: "Claude" },
  { id: "gemini", name: "Gemini" },
  { id: "deepseek", name: "DeepSeek" },
];

export function ProviderConnection({
  workspaceId,
  connections,
  canManage,
}: {
  workspaceId: string;
  connections: Connection[];
  canManage: boolean;
}) {
  const router = useRouter();
  const [items, setItems] = useState(connections);
  const [provider, setProvider] = useState<Connection["provider"]>(
    connections.find((item) => item.state === "active")?.provider || "openai",
  );
  const [key, setKey] = useState("");
  const [modelSearch, setModelSearch] = useState("");
  const [draftModel, setDraftModel] = useState<string | null>(null);
  const [busy, setBusy] = useState<
    "verify" | "model" | "revoke" | "refresh" | null
  >(null);
  const [showSetupOnly, setShowSetupOnly] = useState(false);
  const [confirmRevoke, setConfirmRevoke] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const connection = items.find((item) => item.provider === provider);
  const active = connection?.state === "active";
  const selectedModel = draftModel ?? connection?.default_model_id ?? "";
  const models = active ? connection.verified_models : [];
  const visibleModels = models.filter(
    (id) =>
      id.toLowerCase().includes(modelSearch.trim().toLowerCase()) &&
      (showSetupOnly || connection?.model_capabilities[id]?.runnable),
  );
  const path = `/workspaces/${workspaceId}/integrations/providers/${provider}`;
  const connectedCount = items.filter((item) => item.state === "active").length;

  function remember(updated: Connection) {
    setItems((previous) => [
      ...previous.filter((item) => item.provider !== updated.provider),
      updated,
    ]);
    router.refresh();
  }

  function chooseProvider(value: Connection["provider"]) {
    setProvider(value);
    setKey("");
    setModelSearch("");
    setDraftModel(null);
    setConfirmRevoke(false);
    setError("");
    setNotice("");
  }

  async function verify() {
    setBusy("verify");
    setError("");
    setNotice("");
    try {
      const updated = await api<Connection>(path, {
        method: "POST",
        body: JSON.stringify({ api_key: key }),
      });
      remember(updated);
      setKey("");
      setDraftModel(null);
      setNotice("Key verified. Choose a model from the list below.");
    } catch (cause) {
      setError(
        cause instanceof Error ? cause.message : "Could not verify this key.",
      );
    } finally {
      setBusy(null);
    }
  }

  async function saveModel() {
    if (!selectedModel) return;
    setBusy("model");
    setError("");
    setNotice("");
    try {
      const updated = await api<Connection>(`${path}/default-model`, {
        method: "PATCH",
        body: JSON.stringify({ model_id: selectedModel }),
      });
      remember(updated);
      setDraftModel(null);
      setNotice(
        `${selectedModel} is now the default for new agents using ${updated.display_name}.`,
      );
    } catch (cause) {
      setError(
        cause instanceof Error ? cause.message : "Could not save the model.",
      );
    } finally {
      setBusy(null);
    }
  }

  async function revoke() {
    setBusy("revoke");
    setError("");
    try {
      const updated = await api<Connection>(path, { method: "DELETE" });
      remember(updated);
      setConfirmRevoke(false);
      setDraftModel(null);
      setNotice("Connection revoked and the stored key removed.");
    } catch (cause) {
      setError(
        cause instanceof Error ? cause.message : "Could not revoke this key.",
      );
    } finally {
      setBusy(null);
    }
  }

  async function refreshModels() {
    setBusy("refresh");
    setError("");
    setNotice("");
    try {
      const updated = await api<Connection>(`${path}/refresh-models`, {
        method: "POST",
      });
      remember(updated);
      setDraftModel(null);
      setNotice("Model list refreshed using your saved key.");
    } catch (cause) {
      setError(
        cause instanceof Error ? cause.message : "Could not refresh models.",
      );
    } finally {
      setBusy(null);
    }
  }

  return (
    <>
      <PageHeader
        eyebrow="MODEL CONNECTIONS"
        title="Integrations"
        description="Connect a provider, verify your key, and choose the model your workspace will use by default."
      />
      <div className="integration-shell">
        <section
          className="panel integration-main"
          aria-label="Configure a model provider"
        >
          <div className="integration-heading">
            <div>
              <span className="integration-eyebrow">PROVIDER SETUP</span>
              <h2>Connect a model provider</h2>
              <p>
                One setup flow for every provider. Keys stay encrypted on the
                server.
              </p>
            </div>
            <Badge tone={active ? "green" : "amber"}>
              {active ? "Connected" : "Not connected"}
            </Badge>
          </div>

          {error && <ErrorNotice message={error} />}
          {notice && (
            <div className="integration-notice" role="status">
              <Check size={17} /> {notice}
            </div>
          )}

          <div className="integration-step">
            <span className="integration-step-number">01</span>
            <div className="integration-step-body">
              <h3>Choose provider</h3>
              <p>Select the service that issued your API key.</p>
              <select
                aria-label="Model provider"
                disabled={!!busy}
                value={provider}
                onChange={(event) =>
                  chooseProvider(event.target.value as Connection["provider"])
                }
              >
                {providers.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.name}
                  </option>
                ))}
              </select>
            </div>
          </div>

          <div className="integration-step">
            <span className="integration-step-number">02</span>
            <div className="integration-step-body">
              <h3>Verify API key</h3>
              <p>
                {active
                  ? `Connected with ${connection.masked_hint}. Enter a new key only to rotate it.`
                  : "Enter your key to securely check which models are available."}
              </p>
              {canManage ? (
                <div className="integration-key-row">
                  <label className="integration-key-input">
                    <KeyRound size={17} />
                    <input
                      aria-label={`${providers.find((item) => item.id === provider)?.name} API key`}
                      type="password"
                      autoComplete="off"
                      placeholder="Paste your API key"
                      value={key}
                      onChange={(event) => setKey(event.target.value)}
                    />
                  </label>
                  <Button onClick={verify} disabled={!!busy || !key.trim()}>
                    {busy === "verify" ? (
                      <LoaderCircle className="spin" size={16} />
                    ) : (
                      <ShieldCheck size={16} />
                    )}
                    {active ? "Verify new key" : "Verify key"}
                  </Button>
                </div>
              ) : (
                <p className="field-hint">
                  An owner or admin manages API keys and default models.
                </p>
              )}
              <span className="integration-security">
                <LockKeyhole size={14} /> The key is encrypted and never shown
                again.
              </span>
            </div>
          </div>

          <div className="integration-step">
            <span className="integration-step-number">03</span>
            <div className="integration-step-body">
              <div className="row between">
                <div>
                  <h3>Choose a model</h3>
                  <p>
                    {active
                      ? `${models.length} models returned by ${connection.display_name}.`
                      : "Verify a key to load available models."}
                  </p>
                </div>
                {active && <Badge>{models.length} available</Badge>}
              </div>
              {active ? (
                <>
                  {canManage && (
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={refreshModels}
                      disabled={!!busy}
                    >
                      {busy === "refresh" ? "Refreshing…" : "Refresh models"}
                    </Button>
                  )}
                  <label>
                    <input
                      type="checkbox"
                      checked={showSetupOnly}
                      onChange={(e) => setShowSetupOnly(e.target.checked)}
                    />{" "}
                    Show models for setup only
                  </label>
                  <label className="integration-model-search">
                    <Search size={17} />
                    <input
                      aria-label="Search available models"
                      placeholder="Search models"
                      value={modelSearch}
                      onChange={(event) => setModelSearch(event.target.value)}
                    />
                  </label>
                  <div
                    className="integration-model-list"
                    aria-label="Available models"
                  >
                    {visibleModels.length ? (
                      visibleModels.map((id) => (
                        <button
                          key={id}
                          type="button"
                          aria-pressed={selectedModel === id}
                          className={`integration-model-option ${selectedModel === id ? "selected" : ""}`}
                          onClick={() => setDraftModel(id)}
                        >
                          <span className="integration-radio" />
                          <span>{id}</span>
                          <small>
                            {connection.model_capabilities[id]?.runnable
                              ? "Ready to run"
                              : "Setup only"}
                          </small>
                          {connection.default_model_id === id && (
                            <small>Current default</small>
                          )}
                        </button>
                      ))
                    ) : (
                      <p className="integration-no-models">
                        No models match that search.
                      </p>
                    )}
                  </div>
                  {selectedModel && (
                    <div className="field-hint" role="status">
                      <p>
                        {connection.model_capabilities[selectedModel]?.reason}
                      </p>
                      {connection.model_capabilities[selectedModel]
                        ?.runnable && (
                        <p>
                          Estimated USD per 1M text tokens: $
                          {
                            connection.model_capabilities[selectedModel]
                              .input_usd_per_million
                          }{" "}
                          input / $
                          {
                            connection.model_capabilities[selectedModel]
                              .output_usd_per_million
                          }{" "}
                          output.
                          {connection.model_capabilities[selectedModel]
                            .local_tools
                            ? " Local tools supported."
                            : " Text runs only; local tools unavailable."}
                        </p>
                      )}
                      <p>
                        A model listing does not guarantee generation access or
                        available credit.
                      </p>
                    </div>
                  )}
                  {canManage && (
                    <Button
                      onClick={saveModel}
                      disabled={
                        !!busy ||
                        !selectedModel ||
                        selectedModel === connection.default_model_id
                      }
                    >
                      {busy === "model" ? (
                        <LoaderCircle className="spin" size={16} />
                      ) : (
                        <Check size={16} />
                      )}
                      Save default model
                    </Button>
                  )}
                </>
              ) : (
                <div className="integration-model-empty">
                  <ChevronRight size={19} /> Models appear here after
                  verification.
                </div>
              )}
            </div>
          </div>

          {active && canManage && (
            <div className="integration-danger">
              {confirmRevoke ? (
                <div className="row">
                  <span>Remove this provider&apos;s stored key?</span>
                  <Button
                    size="sm"
                    variant="outline"
                    disabled={!!busy}
                    onClick={revoke}
                  >
                    Confirm revoke
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => setConfirmRevoke(false)}
                  >
                    Cancel
                  </Button>
                </div>
              ) : (
                <button type="button" onClick={() => setConfirmRevoke(true)}>
                  <Trash2 size={15} /> Revoke this connection
                </button>
              )}
            </div>
          )}
        </section>

        <aside className="integration-aside">
          <section className="panel integration-connected">
            <div className="row between">
              <h2>Connected providers</h2>
              <Badge tone="purple">{connectedCount}</Badge>
            </div>
            <p>Choose a provider to review its key and model.</p>
            <div className="integration-provider-list">
              {providers.map((item) => {
                const saved = items.find((entry) => entry.provider === item.id);
                return (
                  <button
                    type="button"
                    key={item.id}
                    className={`integration-provider-row ${provider === item.id ? "current" : ""}`}
                    disabled={!!busy}
                    onClick={() => chooseProvider(item.id)}
                  >
                    <span
                      className={`integration-provider-dot ${saved?.state === "active" ? "active" : ""}`}
                    />
                    <span>
                      <strong>{item.name}</strong>
                      <small>
                        {saved?.state === "active"
                          ? saved.default_model_id || "Model not selected"
                          : "Not connected"}
                      </small>
                    </span>
                    <ChevronRight size={16} />
                  </button>
                );
              })}
            </div>
          </section>
          <section className="integration-help">
            <ShieldCheck size={20} />
            <p>
              Verification checks key access and lists models. It does not run a
              model or confirm billing capacity.
            </p>
          </section>
        </aside>
      </div>
    </>
  );
}
