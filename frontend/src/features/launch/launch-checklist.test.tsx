// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { LaunchChecklist } from "./launch-checklist";
import type { LaunchStep } from "./launch-model";
afterEach(cleanup);
const steps: LaunchStep[] = ["pending", "working", "blocked", "complete"].map(
  (status, index) => ({
    id: (["save", "check", "sample", "publish"] as const)[index],
    title: [
      "Save your draft",
      "Check setup",
      "Try a sample",
      "Publish a version",
    ][index],
    status: status as LaunchStep["status"],
    description: `Explanation ${index}`,
    action: (["save", "check", "sample", "publish"] as const)[index],
  }),
);
it("renders every textual status, warnings and explicit actions without mount effects", () => {
  const onAction = vi.fn(),
    onIssue = vi.fn();
  render(
    <LaunchChecklist
      steps={steps}
      issues={[
        { code: "future", message: "Unknown issue", target: "future-section" },
      ]}
      warnings={[{ code: "warning", message: "Keep this warning" }]}
      canEdit
      onAction={onAction}
      onIssue={onIssue}
    />,
  );
  expect(onAction).not.toHaveBeenCalled();
  expect(onIssue).not.toHaveBeenCalled();
  for (const text of [
    "Pending",
    "Working",
    "Blocked",
    "Complete",
    "Keep this warning",
  ])
    expect(screen.getByText(text)).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "Save your draft" }));
  expect(onAction).toHaveBeenCalledWith("save");
  fireEvent.click(
    screen.getByRole("button", { name: /Review issue: Unknown issue/ }),
  );
  expect(onIssue).toHaveBeenCalledWith({
    code: "future",
    message: "Unknown issue",
    target: "future-section",
  });
});
it("disables mutation actions for viewers and retains result inspection", () => {
  render(
    <LaunchChecklist
      steps={[
        ...steps,
        { ...steps[2], action: "result", title: "Inspect result" },
      ]}
      issues={[]}
      warnings={[]}
      canEdit={false}
      onAction={vi.fn()}
      onIssue={vi.fn()}
    />,
  );
  for (const name of [
    "Save your draft",
    "Check setup",
    "Try a sample",
    "Publish a version",
  ])
    expect(
      (screen.getByRole("button", { name }) as HTMLButtonElement).disabled,
    ).toBe(true);
  expect(
    (screen.getByRole("button", { name: "View result" }) as HTMLButtonElement)
      .disabled,
  ).toBe(false);
});
