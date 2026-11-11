import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { TaskStart } from "./task-start";

describe("TaskStart", () => {
  it("renders the three workspace-scoped starting destinations", () => {
    const html = renderToStaticMarkup(
      createElement(TaskStart, { workspaceId: "ws-123" }),
    );

    expect(html).toContain("Choose what to build");
    expect(html).toContain('href="/w/ws-123/templates?focus=support-triage"');
    expect(html).toContain('href="/w/ws-123/agents/new"');
    expect(html).toContain('href="/w/ws-123/workflows"');
  });
});
