import type { Connection } from "@/lib/api/types";

export function isRunnableModel(
  connections: Connection[],
  provider: string,
  modelId: string,
): boolean {
  return connections.some(
    (c) =>
      c.provider === provider &&
      c.state === "active" &&
      c.model_capabilities[modelId]?.runnable,
  );
}
