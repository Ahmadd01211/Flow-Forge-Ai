import type { Edge } from "@xyflow/react";

export function connectInsertedNode(
  edges: Edge[],
  sourceId: string,
  nodeId: string,
  outgoing: Edge | undefined,
  newEdgeId: string,
): Edge[] {
  if (!outgoing) {
    return [...edges, { id: newEdgeId, source: sourceId, target: nodeId, sourceHandle: "out", targetHandle: "in", type: "smoothstep", data: { mappings: [] } }];
  }
  return [
    ...edges.map((edge) => edge.id === outgoing.id ? { ...edge, target: nodeId } : edge),
    { id: newEdgeId, source: nodeId, target: outgoing.target, sourceHandle: "out", targetHandle: "in", type: "smoothstep", data: { mappings: [] } },
  ];
}
