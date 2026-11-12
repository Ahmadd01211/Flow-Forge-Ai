import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { TaskStart } from "./task-start";

describe("TaskStart", () => {
  it("renders the workspace-scoped starting destinations", () => {
    const html = renderToStaticMarkup(
      createElement(TaskStart, { workspaceId: "ws-123" }),
    );

    expect(html).toContain("Choose what to build");
    expect(html).toContain("Try without a model");
    expect(html).toContain(
      'href="/w/ws-123/templates?focus=remove-duplicates"',
    );
    expect(html).toContain('href="/w/ws-123/templates?focus=support-triage"');
    expect(html).toContain('href="/w/ws-123/agents/new"');
    expect(html).toContain('href="/w/ws-123/workflows"');
  });
});
