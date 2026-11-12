"use client";
import { Button } from "@/components/ui/button";
import type { LaunchAction, LaunchIssue, LaunchStep } from "./launch-model";
const statuses = {
  pending: "Pending",
  working: "Working",
  blocked: "Blocked",
  complete: "Complete",
};
export function LaunchChecklist({
  steps,
  issues,
  warnings,
  canEdit,
  onAction,
  onIssue,
}: {
  steps: LaunchStep[];
  issues: LaunchIssue[];
  warnings: LaunchIssue[];
  canEdit: boolean;
  onAction: (action: LaunchAction) => void;
  onIssue: (issue: LaunchIssue) => void;
}) {
  return (
    <section className="launch-checklist" aria-label="Launch checklist">
      <h2>Launch checklist</h2>
      <ol className="launch-checklist-steps">
        {steps.map((step) => (
          <li key={step.id} className="launch-checklist-step">
            <div className="launch-checklist-copy">
              <strong>{step.title}</strong>
              <span className="launch-checklist-status">
                {statuses[step.status]}
              </span>
              <p>{step.description}</p>
            </div>
            {step.action && (
              <Button
                type="button"
                variant="outline"
                disabled={!canEdit && step.action !== "result"}
                onClick={() => onAction(step.action!)}
              >
                {step.action === "result"
                  ? "View result"
                  : step.action === "configure"
                    ? "Configure setup"
                    : step.title}
              </Button>
            )}
          </li>
        ))}
      </ol>
      {issues.length > 0 && (
        <div className="launch-checklist-notices">
          <h3>Setup issues</h3>
          <ul>
            {issues.map((issue, i) => (
              <li key={`${issue.code}-${i}`}>
                <Button
                  type="button"
                  variant="ghost"
                  onClick={() => onIssue(issue)}
                  aria-label={`Review issue: ${issue.message}`}
                >
                  {issue.message}
                </Button>
              </li>
            ))}
          </ul>
        </div>
      )}
      {warnings.length > 0 && (
        <div className="launch-checklist-notices">
          <h3>Warnings</h3>
          <ul>
            {warnings.map((warning, i) => (
              <li key={`${warning.code}-${i}`}>{warning.message}</li>
            ))}
          </ul>
        </div>
      )}
      {!canEdit && (
        <p className="launch-checklist-permission">
          You have read-only access. An editor can save, check, test and
          publish.
        </p>
      )}
    </section>
  );
}
