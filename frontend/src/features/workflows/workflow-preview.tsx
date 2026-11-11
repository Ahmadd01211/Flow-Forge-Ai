import type { GraphNode } from "@/lib/api/types";
import { selectedPathLabel } from "./node-config";

export function PreviewSteps({
  nodes,
  steps,
}: {
  nodes: GraphNode[];
  steps: { node_id: string; status: string; selected_port?: string | null }[];
}) {
  return (
    <small>
      {steps
        .map((step) => {
          const node = nodes.find((item) => item.id === step.node_id);
          return `${node?.label ?? step.node_id}: ${step.status}${step.selected_port ? ` · ${selectedPathLabel(step.selected_port, node)}` : ""}`;
        })
        .join(" → ")}
    </small>
  );
}
