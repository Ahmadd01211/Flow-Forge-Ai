import { describe, expect, it } from "vitest";
import {
  prioritizeTemplate,
  startingChoices,
  templatePresentation,
  filterRecipes,
  discoverRecipes,
} from "./task-start-model";

describe("guided task start", () => {
  const goals = [
    {
      key: "support-triage",
      name: "Support ticket triage",
      description: "Classify an incoming ticket and explain the priority.",
      category: "Support",
    },
    {
      key: "customer-reply-draft",
      name: "Customer reply draft",
      description: "Draft a customer reply using brand guidance.",
      category: "Support",
    },
    {
      key: "faq-answer",
      name: "FAQ answer assistant",
      description: "Answer a question using only supplied reference material.",
      category: "Knowledge",
    },
  ];

  it("ranks a natural goal by meaningful task words and recommends its closest recipe", () => {
    const result = discoverRecipes(
      goals,
      "I want to answer customer questions",
      "all",
    );
    expect(
      result.map(({ template, recommended }) => [template.key, recommended]),
    ).toEqual([
      ["faq-answer", true],
      ["customer-reply-draft", false],
    ]);
    expect(
      filterRecipes(goals, "Can you help me sort urgent tickets?", "all").map(
        (r) => r.key,
      ),
    ).toEqual(["support-triage"]);
    expect(goals.map((r) => r.key)).toEqual([
      "support-triage",
      "customer-reply-draft",
      "faq-answer",
    ]);
  });

  it("retains partial task search while ranking complete goal words", () => {
    expect(filterRecipes(goals, "refer", "all").map((r) => r.key)).toEqual([
      "faq-answer",
    ]);
  });

  it("recommends within a category without a focus URL and respects an available explicit focus", () => {
    expect(
      discoverRecipes(goals, "", "Support").map(({ template, recommended }) => [
        template.key,
        recommended,
      ]),
    ).toEqual([
      ["support-triage", true],
      ["customer-reply-draft", false],
    ]);
    expect(
      discoverRecipes(goals, "", "Support", "customer-reply-draft")[0],
    ).toEqual({ template: goals[1], recommended: true });
    expect(discoverRecipes(goals, "", "Support", "missing")[0]).toEqual({
      template: goals[0],
      recommended: true,
    });
    expect(
      discoverRecipes(goals, "I want to", "all").every((r) => !r.recommended),
    ).toBe(true);
    expect(discoverRecipes(goals, "astronomy", "Support")).toEqual([]);
  });
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
