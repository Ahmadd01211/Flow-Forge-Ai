import { describe, expect, it } from "vitest";
import {
  prioritizeTemplate,
  startingChoices,
  templatePresentation,
  filterRecipes,
} from "./task-start-model";

describe("guided task start", () => {
  it("searches task words without a provider call and combines category selection", () => {
    const recipes = [
      {
        key: "faq",
        name: "Answer questions",
        description: "Use reference material",
        category: "Knowledge",
      },
      {
        key: "reply",
        name: "Customer reply",
        description: "Answer a customer",
        category: "Support",
      },
    ];
    expect(
      filterRecipes(recipes, " ANSWER ", "Support").map((r) => r.key),
    ).toEqual(["reply"]);
    expect(
      filterRecipes(recipes, "reference", "all").map((r) => r.key),
    ).toEqual(["faq"]);
    expect(filterRecipes(recipes, "missing", "all")).toEqual([]);
    expect(filterRecipes(recipes, "", "all")).toEqual(recipes);
  });
  it("routes each starting choice within the active workspace", () => {
    expect(
      startingChoices("/w/ws-123").map(({ key, href }) => [key, href]),
    ).toEqual([
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

  it("marks only an available focused template as recommended", () => {
    const templates = [{ key: "faq-answer" }, { key: "support-triage" }];

    expect(templatePresentation(templates, "support-triage")).toEqual([
      { template: { key: "support-triage" }, recommended: true },
      { template: { key: "faq-answer" }, recommended: false },
    ]);
    expect(templatePresentation(templates, "not-installed")).toEqual([
      { template: { key: "faq-answer" }, recommended: false },
      { template: { key: "support-triage" }, recommended: false },
    ]);
  });
});
