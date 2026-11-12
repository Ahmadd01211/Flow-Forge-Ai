/** Optional recipe examples initialize sample forms only, never saved authoring state. */
export interface RecipeSample {
  sampleInput?: Record<string, unknown>;
  expectedResult?: string;
}

export async function loadRecipeSample(
  key: unknown,
  kind: "agent" | "workflow",
  fetch: (path: string) => Promise<unknown>,
): Promise<RecipeSample | undefined> {
  if (typeof key !== "string" || !/^[a-zA-Z0-9][a-zA-Z0-9_-]{0,127}$/.test(key))
    return;
  try {
    const value = await fetch(`/templates/${encodeURIComponent(key)}`);
    if (!value || typeof value !== "object" || Array.isArray(value)) return;
    const recipe = value as Record<string, unknown>;
    if (recipe.kind !== kind) return;
    if (
      recipe.sample_input !== undefined &&
      (!recipe.sample_input ||
        typeof recipe.sample_input !== "object" ||
        Array.isArray(recipe.sample_input))
    )
      return;
    if (
      recipe.expected_result !== undefined &&
      typeof recipe.expected_result !== "string"
    )
      return;
    return {
      ...(recipe.sample_input !== undefined
        ? { sampleInput: recipe.sample_input as Record<string, unknown> }
        : {}),
      ...(recipe.expected_result
        ? { expectedResult: recipe.expected_result as string }
        : {}),
    };
  } catch {
    // Examples are optional: unavailable/private/deleted recipes cannot block an editor.
    return;
  }
}
