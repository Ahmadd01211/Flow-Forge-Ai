import type { Agent, AgentVersion } from "@/lib/api/types";
export interface VersionChange {
  path: string;
  before: unknown;
  after: unknown;
}
function object(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}
function normalize(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(normalize);
  if (object(value))
    return Object.fromEntries(
      Object.keys(value)
        .sort()
        .map((key) => [key, normalize(value[key])]),
    );
  return value;
}
function canonical(value: unknown): string | undefined {
  return JSON.stringify(normalize(value));
}
export function compareDefinitions(
  before: Pick<AgentVersion, "name" | "description" | "config">,
  after: Pick<Agent, "name" | "description" | "config">,
): VersionChange[] {
  const changes: VersionChange[] = [];
  function walk(a: unknown, b: unknown, path: string) {
    if (canonical(a) === canonical(b)) return;
    if (object(a) && object(b)) {
      for (const key of [
        ...new Set([...Object.keys(a), ...Object.keys(b)]),
      ].sort())
        walk(
          a[key],
          b[key],
          `${path}/${key.replaceAll("~", "~0").replaceAll("/", "~1")}`,
        );
    } else changes.push({ path, before: a, after: b });
  }
  for (const field of ["name", "description", "config"] as const)
    walk(before[field], after[field], `/${field}`);
  return changes;
}
export function displayValue(value: unknown) {
  return value === undefined
    ? "(not present)"
    : typeof value === "string"
      ? value
      : JSON.stringify(value, null, 2);
}
