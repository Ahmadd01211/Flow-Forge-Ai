export type StartingChoice = {
  key: "support-triage" | "blank-agent" | "blank-workflow";
  title: string;
  description: string;
  href: string;
};

export function startingChoices(base: string): StartingChoice[] {
  return [
    {
      key: "support-triage",
      title: "Support ticket triage",
      description: "Start with an editable ticket classifier and try a sample ticket.",
      href: `${base}/templates?focus=support-triage`,
    },
    {
      key: "blank-agent",
      title: "Start with a blank agent",
      description: "Set up one focused assistant with your own instructions and fields.",
      href: `${base}/agents/new`,
    },
    {
      key: "blank-workflow",
      title: "Start with a blank workflow",
      description: "Build a repeatable process from connected steps.",
      href: `${base}/workflows`,
    },
  ];
}

export function prioritizeTemplate<T extends { key: string }>(
  items: T[],
  focus?: string,
): T[] {
  if (!focus) return items;

  const index = items.findIndex((item) => item.key === focus);
  if (index <= 0) return items;

  return [items[index], ...items.slice(0, index), ...items.slice(index + 1)];
}

export function templatePresentation<T extends { key: string }>(
  items: T[],
  focus?: string,
): { template: T; recommended: boolean }[] {
  const recommendedKey = focus && items.some((item) => item.key === focus)
    ? focus
    : undefined;

  return prioritizeTemplate(items, focus).map((template) => ({
    template,
    recommended: template.key === recommendedKey,
  }));
}
