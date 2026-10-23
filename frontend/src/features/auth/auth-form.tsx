"use client";
import { useState } from "react";
import Link from "next/link";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import {
  ArrowRight,
  Eye,
  EyeOff,
  LoaderCircle,
  ShieldCheck,
  Workflow,
} from "lucide-react";
import { Brand } from "@/components/shared/brand";
import { Button } from "@/components/ui/button";
import { ErrorNotice } from "@/components/shared/ui";
import { api } from "@/lib/api/client";
import type { SessionData } from "@/lib/api/types";
import { authSchema } from "./validation";

export function AuthForm({ mode }: { mode: "login" | "register" }) {
  const [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [show, setShow] = useState(false);
  const isRegister = mode === "register";
  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<z.infer<ReturnType<typeof authSchema>>>({
    resolver: zodResolver(authSchema(mode)),
  });
  async function submit(data: z.infer<ReturnType<typeof authSchema>>) {
    setBusy(true);
    setError("");
    try {
      const result = await api<SessionData>(`/auth/${mode}`, {
        method: "POST",
        body: JSON.stringify(data),
      });
      window.location.assign(
        result.workspaces.length
          ? `/w/${result.workspaces[0].id}/overview`
          : "/workspaces",
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unable to sign in.");
      setBusy(false);
    }
  }
  return (
    <div className="auth-page">
      <aside className="auth-story">
        <Link href="/">
          <Brand />
        </Link>
        <div>
          <span className="hero-label">BUILD WITH INTENT</span>
          <h1>
            Great work starts
            <br />
            with a clear flow.
          </h1>
          <p>
            A home for your agents, your workflows, and everything that connects
            them.
          </p>
          <div className="auth-illustration">
            <Workflow size={62} />
            <span className="auth-connector" />
            <div>
              <strong>Your next workflow</strong>
              <span>Starts with one good idea.</span>
            </div>
          </div>
        </div>
        <span className="auth-story-footer">
          <ShieldCheck size={16} /> Your workspace. Your permissions. Your
          control.
        </span>
      </aside>
      <main className="auth-main">
        <div className="auth-form-wrap">
          <Link href="/" className="back-link">
            ← Back to FlowForge
          </Link>
          <div className="eyebrow">
            {isRegister ? "LET’S GET YOU BUILDING" : "WELCOME BACK"}
          </div>
          <h1>
            {isRegister ? "Create your workspace" : "Sign in to FlowForge"}
          </h1>
          <p>
            {isRegister
              ? "Bring your first agent to life, one step at a time."
              : "Your agents and workflows are right where you left them."}
          </p>
          {error && <ErrorNotice message={error} />}
          <form
            noValidate
            onSubmit={handleSubmit(submit)}
            className="form-stack"
          >
            {isRegister && (
              <>
                <label>
                  Your name
                  <input
                    {...register("name")}
                    aria-invalid={!!errors.name}
                    autoComplete="name"
                    maxLength={100}
                    placeholder="Alex Morgan"
                  />
                  {errors.name && (
                    <span role="alert" className="field-error">
                      {errors.name.message}
                    </span>
                  )}
                </label>
                <label>
                  Workspace name
                  <input
                    {...register("workspace_name")}
                    aria-invalid={!!errors.workspace_name}
                    maxLength={100}
                    placeholder="Acme operations"
                  />
                  {errors.workspace_name && (
                    <span role="alert" className="field-error">
                      {errors.workspace_name.message}
                    </span>
                  )}
                </label>
              </>
            )}
            <label>
              Email address
              <input
                {...register("email")}
                aria-invalid={!!errors.email}
                type="email"
                autoComplete="email"
                placeholder="you@company.com"
              />
              {errors.email && (
                <span role="alert" className="field-error">
                  {errors.email.message}
                </span>
              )}
            </label>
            <label>
              Password
              <div className="password-input">
                <input
                  {...register("password")}
                  aria-invalid={!!errors.password}
                  type={show ? "text" : "password"}
                  maxLength={128}
                  autoComplete={
                    isRegister ? "new-password" : "current-password"
                  }
                  placeholder={
                    isRegister
                      ? "At least 12 characters"
                      : "Enter your password"
                  }
                />
                <button
                  type="button"
                  onClick={() => setShow(!show)}
                  aria-label={show ? "Hide password" : "Show password"}
                >
                  {show ? <EyeOff size={17} /> : <Eye size={17} />}
                </button>
              </div>
              {errors.password ? (
                <span role="alert" className="field-error">
                  {errors.password.message}
                </span>
              ) : (
                isRegister && (
                  <span className="field-hint">
                    Use a unique password with at least 12 characters.
                  </span>
                )
              )}
            </label>
            <Button disabled={busy} type="submit">
              {busy ? <LoaderCircle className="spin" size={17} /> : null}
              {isRegister ? "Create workspace" : "Sign in"}
              <ArrowRight size={17} />
            </Button>
          </form>
          {!isRegister && (
            <p>
              <Link href="/forgot-password">Forgot your password?</Link>
            </p>
          )}
          <p className="auth-switch">
            {isRegister ? "Already have a workspace?" : "New to FlowForge?"}{" "}
            <Link href={isRegister ? "/login" : "/register"}>
              {isRegister ? "Sign in" : "Create an account"}
            </Link>
          </p>
          <div className="auth-security">
            <ShieldCheck size={15} /> HttpOnly session cookies · Server-verified
            access
          </div>
        </div>
      </main>
    </div>
  );
}
