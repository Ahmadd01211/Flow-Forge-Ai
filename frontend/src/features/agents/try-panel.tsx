"use client";
import type { RecipeSample } from "@/features/templates/recipe-handoff";
import { useEffect, useRef, useState } from "react";
import {
  CheckCircle2,
  CircleAlert,
  LoaderCircle,
  MessageSquarePlus,
  Play,
  Send,
  Star,
  Wrench,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api/client";
import type { AgentConfig, AgentRun, RunEvent } from "@/lib/api/types";
import { replyText } from "@/features/workflows/node-config";
import { readFields } from "./schema-fields";
import { isChatInput, toolLabel } from "./builder-model";
import {
  launchConfigKey,
  type SampleEvidence,
} from "@/features/launch/launch-model";
import { FeedbackButtons } from "@/features/executions/feedback";

type Turn =
  | { id: string; role: "user"; text: string }
  | {
      id: string;
      role: "agent";
      pending: boolean;
      text: string;
      input: Record<string, unknown>;
      output?: unknown;
      cost?: string | null;
      tools: RunEvent[];
      error?: string;
      saved?: boolean;
      runId?: string;
    };

const DONE = new Set(["completed", "failed", "cancelled"]);

/**
 * Live test chat for the builder. Every message runs the editor's current settings, saved or
 * not, as a normal budgeted agent run in the agent's hidden playground twin.
 */
export function TryPanel({
  recipeSample,
  workspaceId,
  agentId,
  config,
  schemasValid,
  canEdit,
  configKey,
  onSampleEvent,
}: {
  recipeSample?: RecipeSample;
  configKey?: string;
  onSampleEvent?: (evidence: SampleEvidence) => void;
  workspaceId: string;
  agentId?: string;
  config: AgentConfig;
  schemasValid: boolean;
  canEdit: boolean;
}) {
  const chat = isChatInput(config.input_schema);
  const fields = readFields(JSON.stringify(config.input_schema));
  const usesConversation = !!(
    config.input_schema as { properties?: Record<string, unknown> }
  ).properties?.conversation_id;
  const [turns, setTurns] = useState<Turn[]>([]);
  const [draft, setDraft] = useState(() =>
    typeof recipeSample?.sampleInput?.message === "string"
      ? recipeSample.sampleInput.message
      : "",
  );
  const [form, setForm] = useState<Record<string, string>>(() => {
    const sample = recipeSample?.sampleInput;
    if (!sample) return {};
    return {
      __json: JSON.stringify(sample, null, 2),
      ...Object.fromEntries(
        Object.entries(sample).map(([key, value]) => [
          key,
          typeof value === "string" ? value : JSON.stringify(value),
        ]),
      ),
    };
  });
  const [conversation, setConversation] = useState(() => crypto.randomUUID());
  const [busy, setBusy] = useState(false);
  const end = useRef<HTMLDivElement>(null);
  // Block body: scrollIntoView now returns a Promise, which React would treat as a cleanup function.
  useEffect(() => {
    end.current?.scrollIntoView({ block: "end" });
  }, [turns]);

  const patch = (
    id: string,
    update: Partial<Extract<Turn, { role: "agent" }>>,
  ) =>
    setTurns((current) =>
      current.map((turn) =>
        turn.id === id && turn.role === "agent" ? { ...turn, ...update } : turn,
      ),
    );

  function formInput(): Record<string, unknown> | null {
    if (!fields) {
      try {
        const value = JSON.parse(form.__json ?? "{}");
        return value && typeof value === "object" && !Array.isArray(value)
          ? value
          : null;
      } catch {
        return null;
      }
    }
    return Object.fromEntries(
      fields
        .filter((field) => (form[field.name] ?? "") !== "")
        .map((field) => {
          const raw = form[field.name];
          return [
            field.name,
            field.type === "boolean"
              ? raw === "true"
              : field.type === "number" || field.type === "integer"
                ? Number(raw)
                : raw,
          ];
        }),
    );
  }

  async function send() {
    const input = chat
      ? {
          message: draft.trim(),
          ...(usesConversation ? { conversation_id: conversation } : {}),
        }
      : formInput();
    if (
      !agentId ||
      !canEdit ||
      !schemasValid ||
      !input ||
      (chat && !draft.trim())
    )
      return;
    const replyId = crypto.randomUUID();
    const evidence: SampleEvidence = {
      requestId: replyId,
      configKey: configKey ?? launchConfigKey(config),
      inputKey: launchConfigKey(input),
      mode: "agent_test",
      state: "running",
    };
    const emit = (state: SampleEvidence["state"], runId?: string) =>
      onSampleEvent?.({ ...evidence, state, ...(runId ? { runId } : {}) });
    emit("running");
    setTurns((current) => [
      ...current,
      {
        id: crypto.randomUUID(),
        role: "user",
        text: chat ? draft.trim() : JSON.stringify(input, null, 2),
      },
      { id: replyId, role: "agent", pending: true, text: "", input, tools: [] },
    ]);
    setDraft("");
    setBusy(true);
    let acceptedRunId: string | undefined;
    try {
      const started = await api<{ run: AgentRun }>(
        `/workspaces/${workspaceId}/agents/${agentId}/try`,
        {
          method: "POST",
          headers: { "Idempotency-Key": crypto.randomUUID() },
          body: JSON.stringify({ config, input }),
        },
      );
      let run = started.run;
      acceptedRunId = run.id;
      if (run.state === "waiting") emit("waiting", run.id);
      patch(replyId, { runId: run.id });
      for (let i = 0; i < 90 && !DONE.has(run.state); i++) {
        await new Promise((resolve) => setTimeout(resolve, 1000));
        const [next, events] = await Promise.all([
          api<AgentRun>(`/workspaces/${workspaceId}/runs/${run.id}`),
          api<{ items: RunEvent[] }>(
            `/workspaces/${workspaceId}/runs/${run.id}/events`,
          ),
        ]);
        run = next;
        if (run.state === "waiting") emit("waiting", run.id);
        patch(replyId, {
          tools: events.items.filter(
            (event) => event.kind === "tool" && event.status !== "started",
          ),
        });
      }
      emit(
        run.state === "completed"
          ? "completed"
          : run.state === "failed"
            ? "failed"
            : run.state === "cancelled"
              ? "cancelled"
              : run.state === "waiting"
                ? "waiting"
                : "unknown",
        run.id,
      );
      if (run.state === "completed")
        patch(replyId, {
          pending: false,
          output: run.output,
          text: replyText(run.output),
          cost: run.cost_usd,
        });
      else
        patch(replyId, {
          pending: false,
          error: DONE.has(run.state)
            ? `The run ${run.state}${run.error_code ? ` (${run.error_code})` : ""}.`
            : "Still running. Check Executions for the result.",
        });
    } catch (cause) {
      emit(acceptedRunId ? "unknown" : "failed", acceptedRunId);
      patch(replyId, {
        pending: false,
        error:
          cause instanceof Error ? cause.message : "The test could not start.",
      });
    } finally {
      setBusy(false);
    }
  }

  async function saveExample(turn: Extract<Turn, { role: "agent" }>) {
    try {
      await api(`/workspaces/${workspaceId}/agents/${agentId}/examples`, {
        method: "POST",
        body: JSON.stringify({
          input: turn.input,
          expected_output: turn.output,
        }),
      });
      patch(turn.id, { saved: true });
    } catch (cause) {
      patch(turn.id, {
        error:
          cause instanceof Error
            ? cause.message
            : "Could not save the example.",
      });
    }
  }

  const blocked = !agentId
    ? "Save your draft once to start testing."
    : !canEdit
      ? "You need editor access to run tests."
      : !schemasValid
        ? "Fix the input and output fields first."
        : "";
  return (
    <div className="try-panel">
      <header>
        <div>
          <strong>Try your agent</strong>
          <small>
            Runs your current settings, even unsaved ones. Each message is a
            real, budgeted run.
          </small>
        </div>
        <Button
          size="sm"
          variant="ghost"
          disabled={!turns.length || busy}
          onClick={() => {
            setTurns([]);
            setConversation(crypto.randomUUID());
          }}
          title="Start over"
        >
          <MessageSquarePlus size={14} />
        </Button>
      </header>
      <div className="try-log" aria-live="polite">
        {!turns.length && (
          <div className="try-empty">
            <span aria-hidden="true">👋</span>
            <p>
              {blocked ||
                (chat
                  ? "Say hello and watch your agent think, call tools and reply."
                  : "Fill in the input below and run it to see the output.")}
            </p>
            {chat && config.memory && usesConversation && !blocked && (
              <small>
                Memory is on: this chat is one conversation, kept apart from
                real ones.
              </small>
            )}
          </div>
        )}
        {turns.map((turn) =>
          turn.role === "user" ? (
            <div key={turn.id} className="try-bubble user">
              {turn.text}
            </div>
          ) : (
            <div key={turn.id} className="try-agent">
              {turn.tools.map((event) => (
                <div key={event.id} className={`try-tool ${event.status}`}>
                  <Wrench size={12} />
                  <span>{toolLabel(event.tool_key)}</span>
                  {event.status === "completed" ? (
                    <CheckCircle2 size={12} />
                  ) : (
                    <CircleAlert size={12} />
                  )}
                </div>
              ))}
              {turn.pending ? (
                <div className="try-bubble agent thinking">
                  <span />
                  <span />
                  <span />
                </div>
              ) : turn.error ? (
                <>
                  <div className="try-bubble notice">{turn.error}</div>
                  {turn.runId && (
                    <div className="try-meta">
                      <a
                        href={`/w/${workspaceId}/executions/${turn.runId}`}
                        target="_blank"
                        rel="noreferrer"
                      >
                        See what happened ↗
                      </a>
                    </div>
                  )}
                </>
              ) : (
                <>
                  <div className="try-bubble agent">{turn.text}</div>
                  <div className="try-meta">
                    {turn.cost && <span>${Number(turn.cost).toFixed(4)}</span>}
                    {turn.runId && (
                      <FeedbackButtons
                        workspaceId={workspaceId}
                        runId={turn.runId}
                      />
                    )}
                    {turn.runId && (
                      <a
                        href={`/w/${workspaceId}/executions/${turn.runId}`}
                        target="_blank"
                        rel="noreferrer"
                      >
                        Trace ↗
                      </a>
                    )}
                    <button
                      type="button"
                      disabled={turn.saved}
                      onClick={() => saveExample(turn)}
                    >
                      <Star size={12} />{" "}
                      {turn.saved ? "Saved as test example" : "Save as example"}
                    </button>
                  </div>
                </>
              )}
            </div>
          ),
        )}
        <div ref={end} />
      </div>
      {recipeSample?.expectedResult && (
        <p>Expected example: {recipeSample.expectedResult}</p>
      )}
      {recipeSample && !recipeSample.sampleInput && (
        <p>Enter your own safe sample before testing.</p>
      )}
      {chat ? (
        <form
          className="try-compose"
          onSubmit={(event) => {
            event.preventDefault();
            send();
          }}
        >
          <textarea
            aria-label="Message"
            rows={2}
            value={draft}
            disabled={!!blocked || busy}
            placeholder={blocked || "Type a message…"}
            onChange={(event) => setDraft(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey) {
                event.preventDefault();
                send();
              }
            }}
          />
          <Button
            type="submit"
            size="sm"
            disabled={!!blocked || busy || !draft.trim()}
            aria-label="Send"
          >
            {busy ? (
              <LoaderCircle size={15} className="spin" />
            ) : (
              <Send size={15} />
            )}
          </Button>
        </form>
      ) : (
        <form
          className="try-form"
          onSubmit={(event) => {
            event.preventDefault();
            send();
          }}
        >
          {fields ? (
            fields.map((field) => (
              <label key={field.name}>
                {field.name}
                {field.required ? " *" : ""}
                {field.enum ? (
                  <select
                    value={form[field.name] ?? ""}
                    onChange={(event) =>
                      setForm({ ...form, [field.name]: event.target.value })
                    }
                  >
                    <option value="">Choose…</option>
                    {field.enum.map((option) => (
                      <option key={String(option)} value={String(option)}>
                        {String(option)}
                      </option>
                    ))}
                  </select>
                ) : field.type === "boolean" ? (
                  <select
                    value={form[field.name] ?? ""}
                    onChange={(event) =>
                      setForm({ ...form, [field.name]: event.target.value })
                    }
                  >
                    <option value="">Choose…</option>
                    <option value="true">true</option>
                    <option value="false">false</option>
                  </select>
                ) : (
                  <input
                    type={field.type === "string" ? "text" : "number"}
                    value={form[field.name] ?? ""}
                    placeholder={field.description}
                    onChange={(event) =>
                      setForm({ ...form, [field.name]: event.target.value })
                    }
                  />
                )}
              </label>
            ))
          ) : (
            <label>
              Input JSON
              <textarea
                className="json-editor"
                rows={4}
                value={form.__json ?? "{}"}
                onChange={(event) => setForm({ __json: event.target.value })}
              />
            </label>
          )}
          <Button type="submit" size="sm" disabled={!!blocked || busy}>
            {busy ? (
              <LoaderCircle size={14} className="spin" />
            ) : (
              <Play size={14} />
            )}{" "}
            Run it
          </Button>
        </form>
      )}
    </div>
  );
}
