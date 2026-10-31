"use client";

import { useState } from "react";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api/client";

export function SaveTemplate({
  workspaceId,
  sourceId,
  kind,
  revision,
  name,
  description,
  disabled,
}: {
  workspaceId: string;
  sourceId: string;
  kind: "agent" | "workflow";
  revision: number;
  name: string;
  description: string;
  disabled?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const [title, setTitle] = useState(name);
  const [details, setDetails] = useState(description);
  const [category, setCategory] = useState("Community");
  const [visibility, setVisibility] = useState("private");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [created, setCreated] = useState(false);

  async function submit() {
    setBusy(true);
    setError("");
    try {
      await api(`/workspaces/${workspaceId}/templates`, {
        method: "POST",
        body: JSON.stringify({
          kind,
          source_id: sourceId,
          expected_revision: revision,
          name: title,
          description: details,
          category,
          visibility,
        }),
      });
      setCreated(true);
    } catch (cause) {
      setError(
        cause instanceof Error ? cause.message : "Could not save template.",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <Button
        variant="outline"
        disabled={disabled}
        onClick={() => {
          setOpen(!open);
          setCreated(false);
        }}
        title={
          disabled
            ? "Save your draft before creating a template."
            : "Create a reusable copy of this draft"
        }
      >
        Save as template
      </Button>
      {open && (
        <section
          className="panel"
          aria-label="Save as template"
          style={{
            position: "fixed",
            top: "15%",
            left: "50%",
            transform: "translateX(-50%)",
            width: "min(520px, 94vw)",
            maxHeight: "80vh",
            overflow: "auto",
            zIndex: 100,
            padding: 24,
            boxShadow: "0 12px 60px #0006",
          }}
        >
          <div className="row between">
            <h2>Save as template</h2>
            <Button
              variant="ghost"
              disabled={busy}
              onClick={() => setOpen(false)}
            >
              Close
            </Button>
          </div>
          {created ? (
            <p role="status">
              Template saved.{" "}
              <Link className="text-link" href={`/w/${workspaceId}/templates`}>
                Open template gallery
              </Link>
            </p>
          ) : (
            <>
              <p>
                Create an independent copy of your saved draft. Changes to this
                draft will not update the template.
              </p>
              <label className="field">
                Template name
                <input
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  maxLength={100}
                />
              </label>
              <label className="field">
                Description
                <textarea
                  value={details}
                  onChange={(e) => setDetails(e.target.value)}
                  maxLength={500}
                />
              </label>
              <label className="field">
                Category
                <input
                  value={category}
                  onChange={(e) => setCategory(e.target.value)}
                  maxLength={60}
                />
              </label>
              <label className="field">
                Who can access it?
                <select
                  value={visibility}
                  onChange={(e) => setVisibility(e.target.value)}
                >
                  <option value="private">Only me</option>
                  <option value="workspace">Members of this workspace</option>
                  <option value="public">Everyone signed in</option>
                </select>
              </label>
              <p className="field-hint">
                Review instructions, descriptions and fixed values for private
                information before sharing. Connected credentials are excluded.
                Agent, integration and trigger steps must be configured in each
                copy.
              </p>
              {error && <p role="alert">{error}</p>}
              <Button
                disabled={busy || !title.trim() || !category.trim()}
                onClick={submit}
              >
                {busy ? "Saving?" : "Create template"}
              </Button>
            </>
          )}
        </section>
      )}
    </div>
  );
}
