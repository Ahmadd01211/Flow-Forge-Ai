"use client";
import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { ArrowLeft, LoaderCircle, MessageSquarePlus, Send } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ErrorNotice } from "@/components/shared/ui";
import { api } from "@/lib/api/client";
import { replyText } from "./node-config";
import { FeedbackButtons } from "@/features/executions/feedback";

type RunState = "queued" | "running" | "waiting" | "completed" | "failed" | "cancelled";
type ChatRun = { id: string; state: RunState; output: unknown; error_code: string | null };
type Message = { id: string; role: "user" | "assistant" | "notice"; text: string; pending?: boolean; runId?: string };

export function WorkflowChat({ workspaceId, workflowId, name }: { workspaceId: string; workflowId: string; name: string }) {
  return (
    <RunChat
      title={name}
      subtitle="runs the latest published version"
      backHref={`/w/${workspaceId}/workflows/${workflowId}/edit`}
      backLabel="Back to the workflow editor"
      sendPath={`/workspaces/${workspaceId}/workflows/${workflowId}/chat`}
      pollPath={(id) => `/workspaces/${workspaceId}/workflow-runs/${id}`}
      emptyText="Send a message to start a run. Each message carries the same conversation ID, so an LLM step with memory remembers what was said."
    />
  );
}

/** A chat over runs: each message starts a run through `sendPath`, polled at `pollPath(runId)`. */
export function RunChat({ title, subtitle, backHref, backLabel, sendPath, pollPath, emptyText, agentRuns }: {
  title: string;
  subtitle: string;
  backHref: string;
  backLabel: string;
  sendPath: string;
  pollPath: (runId: string) => string;
  emptyText: string;
  /** For agent runs: show thumbs up/down and a trace link on each reply. */
  agentRuns?: { workspaceId: string };
}) {
  const [conversation, setConversation] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const end = useRef<HTMLDivElement>(null);
  // Block body: scrollIntoView now returns a Promise, which React would treat as a cleanup function.
  useEffect(() => {
    end.current?.scrollIntoView({ block: "end" });
  }, [messages]);

  function settle(id: string, update: Partial<Message>) {
    setMessages((current) => current.map((message) => (message.id === id ? { ...message, ...update, pending: false } : message)));
  }

  async function send() {
    const text = draft.trim();
    if (!text || busy) return;
    const replyId = crypto.randomUUID();
    setDraft("");
    setError("");
    setBusy(true);
    setMessages((current) => [
      ...current,
      { id: crypto.randomUUID(), role: "user", text },
      { id: replyId, role: "assistant", text: "", pending: true },
    ]);
    try {
      const sent = await api<{ conversation_id: string; run: ChatRun }>(sendPath, {
        method: "POST",
        headers: { "Idempotency-Key": crypto.randomUUID() },
        body: JSON.stringify({ message: text, ...(conversation ? { conversation_id: conversation } : {}) }),
      });
      setConversation(sent.conversation_id);
      let run = sent.run;
      for (let i = 0; i < 90 && (run.state === "queued" || run.state === "running"); i++) {
        await new Promise((resolve) => setTimeout(resolve, 1000));
        run = await api<ChatRun>(pollPath(run.id));
      }
      if (run.state === "completed") settle(replyId, { text: replyText(run.output), runId: run.id });
      else if (run.state === "waiting") settle(replyId, { role: "notice", text: "This run is waiting for an approval. The reply arrives once it is approved in Runs." });
      else if (run.state === "queued" || run.state === "running") settle(replyId, { role: "notice", text: "Still working. Check Runs for the result." });
      else settle(replyId, { role: "notice", text: `The run ${run.state}${run.error_code ? ` (${run.error_code})` : ""}.` });
    } catch (cause) {
      setMessages((current) => current.filter((message) => message.id !== replyId));
      setError(cause instanceof Error ? cause.message : "The message could not be sent.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="workflow-chat">
      <header className="workflow-chat-header">
        <Link href={backHref} className="icon-button" aria-label={backLabel}>
          <ArrowLeft size={18} />
        </Link>
        <div>
          <strong>{title}</strong>
          <span className="muted">{conversation ? `Conversation ${conversation.slice(0, 8)}` : "New conversation"} · {subtitle}</span>
        </div>
        <Button variant="outline" size="sm" disabled={busy || !messages.length} onClick={() => { setConversation(null); setMessages([]); setError(""); }}>
          <MessageSquarePlus size={14} />
          New conversation
        </Button>
      </header>
      <div className="workflow-chat-log" aria-live="polite">
        {!messages.length && (
          <p className="workflow-chat-empty">
            {emptyText}
          </p>
        )}
        {messages.map((message) => (
          <div key={message.id} className={`chat-bubble ${message.role}`}>
            {message.pending ? <LoaderCircle size={14} className="spin" aria-label="Waiting for the reply" /> : message.text}
            {agentRuns && message.runId && (
              <span className="chat-meta">
                <FeedbackButtons workspaceId={agentRuns.workspaceId} runId={message.runId} />
                <a href={`/w/${agentRuns.workspaceId}/executions/${message.runId}`} target="_blank" rel="noreferrer">Trace ↗</a>
              </span>
            )}
          </div>
        ))}
        <div ref={end} />
      </div>
      {error && <ErrorNotice message={error} />}
      <form
        className="workflow-chat-compose"
        onSubmit={(event) => {
          event.preventDefault();
          send();
        }}
      >
        <textarea
          aria-label="Message"
          rows={2}
          maxLength={4000}
          value={draft}
          placeholder="Type a message. Enter sends, Shift+Enter adds a line."
          onChange={(event) => setDraft(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter" && !event.shiftKey) {
              event.preventDefault();
              send();
            }
          }}
        />
        <Button type="submit" disabled={busy || !draft.trim()}>
          {busy ? <LoaderCircle size={15} className="spin" /> : <Send size={15} />}
          Send
        </Button>
      </form>
    </div>
  );
}
