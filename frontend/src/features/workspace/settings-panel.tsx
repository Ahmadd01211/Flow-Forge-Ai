"use client";
import { useEffect, useState } from "react";
import { api } from "@/lib/api/client";
import type { SessionData } from "@/lib/api/types";
import { Button } from "@/components/ui/button";
import { Badge, ErrorNotice, PageHeader } from "@/components/shared/ui";

type Role = "owner" | "admin" | "editor" | "viewer";
type Member = {
  id: string;
  user_id: string;
  name: string;
  email: string;
  role: Role;
};
type Invitation = {
  id: string;
  email: string;
  role: string;
  expires_at: string;
};

export function SettingsPanel({
  workspaceId,
  session,
}: {
  workspaceId: string;
  session: SessionData;
}) {
  const workspace = session.workspaces.find((w) => w.id === workspaceId)!;
  const admin = workspace.role === "owner" || workspace.role === "admin";
  const [members, setMembers] = useState<Member[]>([]);
  const [invitations, setInvitations] = useState<Invitation[]>([]);
  const [name, setName] = useState(workspace.name);
  const [newName, setNewName] = useState("");
  const [email, setEmail] = useState("");
  const [role, setRole] = useState("editor");
  const [currentPassword, setCurrentPassword] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const base = `/workspaces/${workspaceId}`;
  async function reload() {
    const [m, i] = await Promise.all([
      api<{ items: Member[] }>(`${base}/members`),
      api<{ items: Invitation[] }>(`${base}/invitations`),
    ]);
    setMembers(m.items);
    setInvitations(i.items);
  }
  useEffect(() => {
    if (!admin) return;
    let active = true;
    Promise.all([
      api<{ items: Member[] }>(`${base}/members`),
      api<{ items: Invitation[] }>(`${base}/invitations`),
    ])
      .then(([m, i]) => {
        if (active) {
          setMembers(m.items);
          setInvitations(i.items);
        }
      })
      .catch((cause) => {
        if (active)
          setError(
            cause instanceof Error
              ? cause.message
              : "Could not load your team.",
          );
      });
    return () => {
      active = false;
    };
  }, [base, admin]);
  async function act(
    path: string,
    method: string,
    body?: unknown,
    success = "Saved.",
    redirect?: string,
  ) {
    setBusy(true);
    setError("");
    setMessage("");
    try {
      await api(path, {
        method,
        body: body === undefined ? undefined : JSON.stringify(body),
      });
      if (redirect) {
        window.location.assign(redirect);
        return;
      }
      setMessage(success);
      if (admin) await reload();
    } catch (cause) {
      setError(
        cause instanceof Error ? cause.message : "Could not save changes.",
      );
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <PageHeader
        eyebrow="YOUR WORKSPACE"
        title="Settings"
        description="Manage your account, workspace and team access."
      />
      {error && <ErrorNotice message={error} />}
      {message && <p role="status">{message}</p>}
      <div className="settings-grid">
        <section className="panel settings-section">
          <h2>Your account</h2>
          <p>
            {session.user.name} · {session.user.email}
          </p>
          <Badge tone={session.user.email_verified ? "green" : "amber"}>
            {session.user.email_verified
              ? "Email verified"
              : "Verify your email"}
          </Badge>
          {!session.user.email_verified && (
            <>
              <p>
                Verify your email before inviting teammates or accepting an
                invitation.
              </p>
              <Button
                disabled={busy}
                onClick={() =>
                  act(
                    "/auth/verification-email",
                    "POST",
                    undefined,
                    "Verification email queued. Check your inbox.",
                  )
                }
              >
                Send verification email
              </Button>
            </>
          )}
          <p>Your role: {workspace.role}</p>
        </section>
        <section className="panel settings-section">
          <h2>Password and sessions</h2>
          <form
            className="form-stack"
            onSubmit={(e) => {
              e.preventDefault();
              void act(
                "/auth/change-password",
                "POST",
                { current_password: currentPassword, password },
                "",
                "/login",
              );
            }}
          >
            <label>
              Current password
              <input
                required
                type="password"
                maxLength={128}
                autoComplete="current-password"
                value={currentPassword}
                onChange={(e) => setCurrentPassword(e.target.value)}
              />
            </label>
            <label>
              New password
              <input
                required
                type="password"
                minLength={12}
                maxLength={128}
                autoComplete="new-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
            </label>
            <Button disabled={busy} type="submit">
              Change password and sign out
            </Button>
          </form>
          <p>Changing your password signs out all devices.</p>
          <Button
            variant="outline"
            disabled={busy}
            onClick={() =>
              act("/auth/logout-all", "POST", undefined, "", "/login")
            }
          >
            Sign out all devices
          </Button>
        </section>
        {admin && (
          <section className="panel settings-section">
            <h2>Workspace details</h2>
            <form
              className="form-stack"
              onSubmit={(e) => {
                e.preventDefault();
                void act(
                  base,
                  "PATCH",
                  { name },
                  "Workspace renamed. Refresh to update navigation.",
                );
              }}
            >
              <label>
                Workspace name
                <input
                  required
                  maxLength={100}
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                />
              </label>
              <Button disabled={busy} type="submit">
                Save workspace name
              </Button>
            </form>
          </section>
        )}
        <section className="panel settings-section">
          <h2>Your workspaces</h2>
          <ul>
            {session.workspaces.map((w) => (
              <li key={w.id}>
                <a href={`/w/${w.id}/overview`}>{w.name}</a> · {w.role}
              </li>
            ))}
          </ul>
          <form
            className="form-stack"
            onSubmit={async (e) => {
              e.preventDefault();
              setBusy(true);
              setError("");
              try {
                const result = await api<{ id: string }>("/workspaces", {
                  method: "POST",
                  body: JSON.stringify({ name: newName }),
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
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
              />
            </label>
            <Button variant="outline" disabled={busy} type="submit">
              Create another workspace
            </Button>
          </form>
        </section>
      </div>
      {admin && (
        <section className="panel settings-section">
          <h2>Team members</h2>
          <p>
            Owners manage administrators and ownership. Administrators manage
            editors and viewers. At least one owner must remain.
          </p>
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Member</th>
                  <th>Role</th>
                  <th>Access</th>
                </tr>
              </thead>
              <tbody>
                {members.map((m) => (
                  <tr key={m.id}>
                    <td>
                      {m.name}
                      <br />
                      <small>{m.email}</small>
                    </td>
                    <td>
                      <select
                        aria-label={`Role for ${m.name}`}
                        value={m.role}
                        disabled={
                          busy ||
                          (workspace.role !== "owner" &&
                            ["owner", "admin"].includes(m.role))
                        }
                        onChange={(e) => {
                          if (
                            window.confirm(
                              `Change ${m.name}'s role to ${e.target.value}?`,
                            )
                          )
                            void act(`${base}/members/${m.id}`, "PATCH", {
                              role: e.target.value,
                            });
                        }}
                      >
                        {(workspace.role === "owner"
                          ? ["owner", "admin", "editor", "viewer"]
                          : [m.role, "editor", "viewer"].filter(
                              (v, i, a) => a.indexOf(v) === i,
                            )
                        ).map((r) => (
                          <option key={r}>{r}</option>
                        ))}
                      </select>
                    </td>
                    <td>
                      <Button
                        variant="outline"
                        size="sm"
                        disabled={
                          busy ||
                          m.role === "owner" ||
                          (workspace.role !== "owner" && m.role === "admin")
                        }
                        onClick={() => {
                          if (window.confirm(`Remove ${m.name}'s access?`))
                            void act(
                              `${base}/members/${m.id}`,
                              "DELETE",
                              undefined,
                              "Member removed.",
                            );
                        }}
                      >
                        Remove
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <h3>Invite a teammate</h3>
          <form
            className="form-stack"
            onSubmit={(e) => {
              e.preventDefault();
              void act(
                `${base}/invitations`,
                "POST",
                { email, role },
                "Invitation emailed. It expires in seven days.",
              );
            }}
          >
            <label>
              Email
              <input
                required
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
              />
            </label>
            <label>
              Role
              <select value={role} onChange={(e) => setRole(e.target.value)}>
                {(workspace.role === "owner"
                  ? ["admin", "editor", "viewer"]
                  : ["editor", "viewer"]
                ).map((r) => (
                  <option key={r}>{r}</option>
                ))}
              </select>
            </label>
            <Button
              disabled={busy || !session.user.email_verified}
              type="submit"
            >
              Send invitation
            </Button>
          </form>
          <h3>Pending invitations</h3>
          {invitations.length ? (
            invitations.map((i) => (
              <div className="row between" key={i.id}>
                <p>
                  {i.email} · {i.role} · expires{" "}
                  {new Date(i.expires_at).toLocaleDateString()}
                </p>
                <Button
                  variant="outline"
                  size="sm"
                  disabled={
                    busy || (workspace.role !== "owner" && i.role === "admin")
                  }
                  onClick={() =>
                    act(
                      `${base}/invitations/${i.id}`,
                      "DELETE",
                      undefined,
                      "Invitation revoked.",
                    )
                  }
                >
                  Revoke
                </Button>
              </div>
            ))
          ) : (
            <p>No pending invitations.</p>
          )}
        </section>
      )}
    </>
  );
}
