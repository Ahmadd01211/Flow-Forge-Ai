"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";
import {
  Bot,
  ChartNoAxesCombined,
  ChevronDown,
  ChevronRight,
  CircleHelp,
  Code2,
  Globe2,
  GitBranch,
  LayoutDashboard,
  LayoutGrid,
  LogOut,
  Menu,
  Play,
  Plug,
  Settings,
  ShieldCheck,
  X,
} from "lucide-react";
import { Brand } from "./brand";
import { api } from "@/lib/api/client";
import type { SessionData, Workspace } from "@/lib/api/types";

const nav = [
  { href: "overview", label: "Overview", icon: LayoutDashboard },
  { href: "agents", label: "Agents", icon: Bot },
  { href: "workflows", label: "Workflows", icon: GitBranch },
  { href: "templates", label: "Templates", icon: LayoutGrid },
  { href: "executions", label: "Executions", icon: Play },
  { href: "deployments", label: "Deployments", icon: Globe2 },
  { href: "tools", label: "Tool Registry", icon: Code2 },
];
const secondary = [
  { href: "integrations", label: "Integrations", icon: Plug },
  { href: "usage", label: "Usage", icon: ChartNoAxesCombined },
  { href: "settings", label: "Settings", icon: Settings },
];
export function AppShell({
  session,
  workspace,
  children,
}: {
  session: SessionData;
  workspace: Workspace;
  children: React.ReactNode;
}) {
  const path = usePathname(),
    [open, setOpen] = useState(false),
    [logoutError, setLogoutError] = useState("");
  const base = `/w/${workspace.id}`,
    builder = path.includes("/workflows/") && path.endsWith("/edit");
  const current = [...nav, ...secondary].find((n) =>
    path.startsWith(`${base}/${n.href}`),
  );
  async function logout() {
    try {
      await api("/auth/logout", { method: "POST" });
      window.location.assign("/login");
    } catch {
      setLogoutError("Could not sign out. Please retry.");
    }
  }
  return (
    <div className={`app-shell ${builder ? "builder-shell" : ""}`}>
      <button
        className={`sidebar-scrim ${open ? "visible" : ""}`}
        aria-label="Close navigation"
        onClick={() => setOpen(false)}
      />
      <aside className={`sidebar ${open ? "open" : ""}`}>
        <Link
          href={`${base}/overview`}
          className="sidebar-brand"
          aria-label="FlowForge overview"
        >
          <Brand compact={builder} />
        </Link>
        <div className="workspace-select">
          <span className="workspace-avatar">
            {workspace.name.slice(0, 1).toUpperCase()}
          </span>
          <div>
            <strong>{workspace.name}</strong>
            <span>Workspace · {workspace.role}</span>
          </div>
          <ChevronDown size={14} />
        </div>
        <span className="nav-section-label">WORKSPACE</span>
        <nav>
          {nav.map((n) => (
            <Link
              title={n.label}
              onClick={() => setOpen(false)}
              className={
                path.startsWith(`${base}/${n.href}`)
                  ? "nav-item active"
                  : "nav-item"
              }
              key={n.href}
              href={`${base}/${n.href}`}
            >
              <n.icon size={19} />
              <span>{n.label}</span>
              {n.href === "workflows" && <span className="nav-new">BUILD</span>}
            </Link>
          ))}
        </nav>
        <div className="nav-secondary">
          {secondary.map((n) => (
            <Link
              title={n.label}
              onClick={() => setOpen(false)}
              className={
                path.startsWith(`${base}/${n.href}`)
                  ? "nav-item active"
                  : "nav-item"
              }
              key={n.href}
              href={`${base}/${n.href}`}
            >
              <n.icon size={19} />
              <span>{n.label}</span>
            </Link>
          ))}
        </div>
        <div className="sidebar-bottom">
          <div className="sidebar-note">
            <ShieldCheck size={18} />
            <strong>Build with confidence</strong>
            <p>Your drafts stay private to your workspace.</p>
          </div>
          <a
            href="/api/docs"
            className="nav-item"
            target="_blank"
            rel="noreferrer"
          >
            <CircleHelp size={18} />
            <span>Developer reference</span>
          </a>
          <div className="user-profile">
            <span className="user-avatar">
              {session.user.name.slice(0, 2).toUpperCase()}
            </span>
            <div>
              <strong>{session.user.name}</strong>
              <span>{workspace.role}</span>
            </div>
            <button onClick={logout} title="Sign out" aria-label="Sign out">
              <LogOut size={17} />
            </button>
          </div>
          {logoutError && <p role="alert">{logoutError}</p>}
        </div>
      </aside>
      <div className="workspace-main">
        <header className="topbar">
          <div className="row">
            <button
              className="mobile-menu icon-button"
              aria-label="Open navigation"
              onClick={() => setOpen(!open)}
            >
              {open ? <X size={20} /> : <Menu size={20} />}
            </button>
            <span className="breadcrumb-workspace">Workspace</span>
            <ChevronRight size={13} />
            <span>{current?.label || "Overview"}</span>
          </div>
          <div className="topbar-right">
            <span className="development-badge">
              <span /> Development workspace
            </span>
            <span className="avatar-small">
              {session.user.name.slice(0, 1).toUpperCase()}
            </span>
          </div>
        </header>
        <main className={builder ? "builder-main" : "page-content"}>
          {children}
        </main>
      </div>
    </div>
  );
}
