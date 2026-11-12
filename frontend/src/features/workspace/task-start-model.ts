export type StartingChoice = {
  key:
    "remove-duplicates" | "support-triage" | "blank-agent" | "blank-workflow";
  title: string;
  description: string;
  href: string;
};

export function startingChoices(base: string): StartingChoice[] {
  return [
    {
      key: "remove-duplicates",
      title: "Try without a model",
      description:
        "Remove duplicate contacts with a ready-to-use sample and expected output. No provider or external connection needed.",
      href: `${base}/templates?focus=remove-duplicates`,
    },
    {
      key: "support-triage",
      title: "Support ticket triage",
      description:
        "Start with an editable ticket classifier and try a sample ticket.",
      href: `${base}/templates?focus=support-triage`,
    },
    {
      key: "blank-agent",
      title: "Start with a blank agent",
      description:
        "Set up one focused assistant with your own instructions and fields.",
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
  const recommendedKey =
    focus && items.some((item) => item.key === focus) ? focus : undefined;

  return prioritizeTemplate(items, focus).map((template) => ({
    template,
    recommended: template.key === recommendedKey,
  }));
}

const goalFiller = new Set(
  "a an and are as at be can could do for from help how i in is it me my of on or our please that the this to use us want we with would you".split(
    " ",
  ),
);

function taskWords(text: string): string[] {
  return [
    ...new Set(
      (text.toLowerCase().match(/[\p{L}\p{N}]+/gu) ?? [])
        .filter((word) => !goalFiller.has(word))
        .map((word) =>
          word.length > 3 && word.endsWith("s") && !word.endsWith("ss")
            ? word.slice(0, -1)
            : word,
        ),
    ),
  ];
}

type SearchableRecipe = {
  name: string;
  description: string;
  category: string;
  key?: string;
};

/** Rank meaningful word overlap locally; unknown goal words do not exclude a task match. */
export function filterRecipes<T extends SearchableRecipe>(
  items: T[],
  query: string,
  category: string,
): T[] {
  const words = taskWords(query);
  return items
    .filter((item) => category === "all" || item.category === category)
    .map((item, index) => {
      const fields = [
        { words: taskWords(item.name), weight: 3 },
        { words: taskWords(item.description), weight: 1 },
        { words: taskWords(item.category), weight: 1 },
        { words: taskWords(item.key ?? ""), weight: 1 },
      ];
      const score = words.reduce(
        (total, word) =>
          total +
          fields.reduce(
            (sum, field) =>
              sum +
              (field.words.some((candidate) => candidate.startsWith(word))
                ? field.weight
                : 0),
            0,
          ),
        0,
      );
      return { item, index, score };
    })
    .filter(({ score }) => !words.length || score > 0)
    .sort((a, b) => b.score - a.score || a.index - b.index)
    .map(({ item }) => item);
}

/** Prefer an explicit available focus; otherwise recommend the best goal/category match. */
export function discoverRecipes<T extends SearchableRecipe & { key: string }>(
  items: T[],
  query: string,
  category: string,
  focus?: string,
): { template: T; recommended: boolean }[] {
  const matches = filterRecipes(items, query, category);
  const recommendation = matches.some((item) => item.key === focus)
    ? focus
    : taskWords(query).length || category !== "all"
      ? matches[0]?.key
      : undefined;
  return templatePresentation(matches, recommendation);
}
