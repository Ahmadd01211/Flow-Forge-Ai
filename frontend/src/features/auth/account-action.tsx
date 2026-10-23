"use client";
import { useState, useSyncExternalStore } from "react";
import Link from "next/link";
import { api } from "@/lib/api/client";
import { Button } from "@/components/ui/button";
import { ErrorNotice } from "@/components/shared/ui";

function subscribeHash(callback: () => void) {
  window.addEventListener("hashchange", callback);
  return () => window.removeEventListener("hashchange", callback);
}

export function AccountAction({
  mode,
}: {
  mode:
    "forgot-password" | "reset-password" | "verify-email" | "accept-invitation";
}) {
  const token = useSyncExternalStore(
    subscribeHash,
    () => window.location.hash.slice(1),
    () => "",
  );
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const title = {
    "forgot-password": "Recover your account",
    "reset-password": "Set a new password",
    "verify-email": "Verify your email",
    "accept-invitation": "Join your team",
  }[mode];
  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const result = await api<{ message?: string; workspace_id?: string }>(
        mode === "accept-invitation"
          ? "/workspaces/accept-invitation"
          : `/auth/${mode}`,
        {
          method: "POST",
          body: JSON.stringify(
            mode === "forgot-password"
              ? { email }
              : mode === "reset-password"
                ? { token, password }
                : { token },
          ),
        },
      );
      window.history.replaceState(null, "", window.location.pathname);
      if (result.workspace_id)
        window.location.assign(`/w/${result.workspace_id}/overview`);
      else setMessage(result.message || "Done.");
    } catch (cause) {
      setError(
        cause instanceof Error
          ? cause.message
          : "Could not complete this request.",
      );
    } finally {
      setBusy(false);
    }
  }
  return (
    <main className="auth-main">
      <div className="auth-form-wrap">
        <Link href="/">← FlowForge AI</Link>
        <h1>{title}</h1>
        {mode === "accept-invitation" && (
          <p>
            Sign in with the invited email and verify it first. Keep this
            invitation open while you do that.
          </p>
        )}
        {error && <ErrorNotice message={error} />}
        {message ? (
          <div>
            <p role="status">{message}</p>
            <Link href="/app">Open your workspace</Link>
          </div>
        ) : (
          <form className="form-stack" onSubmit={submit}>
            {mode === "forgot-password" && (
              <label>
                Email address
                <input
                  required
                  type="email"
                  autoComplete="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                />
              </label>
            )}
            {mode === "reset-password" && (
              <label>
                New password
                <input
                  required
                  minLength={12}
                  maxLength={128}
                  type="password"
                  autoComplete="new-password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                />
                <small>Use at least 12 characters.</small>
              </label>
            )}
            {mode !== "forgot-password" && !token && (
              <p>Open the full link from your email to continue.</p>
            )}
            <Button
              disabled={busy || (mode !== "forgot-password" && !token)}
              type="submit"
            >
              {busy
                ? "Please wait…"
                : mode === "forgot-password"
                  ? "Send recovery email"
                  : "Continue"}
            </Button>
          </form>
        )}
        <p>
          <Link
            href="/login"
            target={mode === "accept-invitation" ? "_blank" : undefined}
          >
            Sign in
          </Link>{" "}
          ·{" "}
          <Link
            href="/register"
            target={mode === "accept-invitation" ? "_blank" : undefined}
          >
            Create an account
          </Link>
        </p>
      </div>
    </main>
  );
}
