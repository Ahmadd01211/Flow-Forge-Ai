"use client";
import { useState } from "react";
import { Send, ThumbsDown, ThumbsUp } from "lucide-react";
import { api } from "@/lib/api/client";
import type { Feedback } from "./trace-model";

/** Thumbs up or down on an agent run; a thumbs down asks what went wrong. */
export function FeedbackButtons({ workspaceId, runId, initial = null }: { workspaceId: string; runId: string; initial?: Feedback["mine"] }) {
  const [mine, setMine] = useState(initial);
  const [comment, setComment] = useState(initial?.comment ?? "");
  const [asking, setAsking] = useState(false);
  const [busy, setBusy] = useState(false);
  const path = `/workspaces/${workspaceId}/runs/${runId}/feedback`;

  async function rate(rating: "up" | "down" | null, text = "") {
    setBusy(true);
    try {
      const result = rating
        ? await api<Feedback>(path, { method: "PUT", body: JSON.stringify({ rating, comment: text }) })
        : await api<Feedback>(path, { method: "DELETE" });
      setMine(result.mine);
      setAsking(rating === "down" && !text);
    } finally {
      setBusy(false);
    }
  }

  return (
    <span className="feedback">
      <button type="button" aria-label="Good answer" aria-pressed={mine?.rating === "up"} className={mine?.rating === "up" ? "on up" : ""} disabled={busy} onClick={() => rate(mine?.rating === "up" ? null : "up")}>
        <ThumbsUp size={12} />
      </button>
      <button type="button" aria-label="Bad answer" aria-pressed={mine?.rating === "down"} className={mine?.rating === "down" ? "on down" : ""} disabled={busy} onClick={() => rate(mine?.rating === "down" ? null : "down")}>
        <ThumbsDown size={12} />
      </button>
      {asking && (
        <form className="feedback-comment" onSubmit={(event) => { event.preventDefault(); rate("down", comment); }}>
          <input aria-label="What went wrong?" placeholder="What went wrong? (optional)" value={comment} maxLength={500} onChange={(event) => setComment(event.target.value)} />
          <button type="submit" aria-label="Send feedback" disabled={busy}><Send size={12} /></button>
        </form>
      )}
    </span>
  );
}
