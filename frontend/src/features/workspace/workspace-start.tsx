"use client";
import { useState } from "react";
import { api } from "@/lib/api/client";
import { Button } from "@/components/ui/button";
import { ErrorNotice } from "@/components/shared/ui";
import type { SessionData } from "@/lib/api/types";

export function WorkspaceStart({ session }: { session: SessionData }) {
  const [name, setName] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  return (
    <main className="auth-main">
      <div className="auth-form-wrap">
        <h1>Your workspaces</h1>
        <p>
          Welcome, {session.user.name}. Open a workspace, create one, or follow
          the invitation in your email.
        </p>
        <ul>
          {session.workspaces.map((w) => (
            <li key={w.id}>
              <a href={`/w/${w.id}/overview`}>{w.name}</a>
            </li>
          ))}
        </ul>
        {error && <ErrorNotice message={error} />}
        <form
          className="form-stack"
          onSubmit={async (e) => {
            e.preventDefault();
            setBusy(true);
            setError("");
            try {
              const result = await api<{ id: string }>("/workspaces", {
                method: "POST",
                body: JSON.stringify({ name }),
              });
              window.location.assign(`/w/${result.id}/overview`);
            } catch (cause) {
              setError(
                cause instanceof Error
                  ? cause.message
                  : "Could not create workspace.",
              );
            } finally {
              setBusy(false);
            }
          }}
        >
          <label>
            New workspace name
            <input
              required
              maxLength={100}
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </label>
          <Button disabled={busy} type="submit">
            Create workspace
          </Button>
        </form>
      </div>
    </main>
  );
}
