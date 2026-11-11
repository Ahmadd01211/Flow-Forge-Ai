import { describe, expect, it } from "vitest";
import { prioritizeTemplate, startingChoices } from "./task-start-model";

describe("guided task start", () => {
  it("routes each starting choice within the active workspace", () => {
    expect(startingChoices("/w/ws-123").map(({ key, href }) => [key, href])).toEqual([
      ["support-triage", "/w/ws-123/templates?focus=support-triage"],
      ["blank-agent", "/w/ws-123/agents/new"],
      ["blank-workflow", "/w/ws-123/workflows"],
    ]);
  });

  it("moves only the focused template to the front", () => {
    const templates = [
      { key: "faq-answer", name: "FAQ" },
      { key: "support-triage", name: "Support" },
      { key: "review-and-release", name: "Review" },
    ];

    expect(prioritizeTemplate(templates, "support-triage")).toEqual([
      { key: "support-triage", name: "Support" },
      { key: "faq-answer", name: "FAQ" },
      { key: "review-and-release", name: "Review" },
    ]);
    expect(templates.map((item) => item.key)).toEqual([
      "faq-answer",
      "support-triage",
      "review-and-release",
    ]);
  });

  it("keeps the gallery order when focus is absent or unknown", () => {
    const templates = [{ key: "faq-answer" }, { key: "support-triage" }];

    expect(prioritizeTemplate(templates)).toEqual(templates);
    expect(prioritizeTemplate(templates, "not-installed")).toEqual(templates);
  });
});
