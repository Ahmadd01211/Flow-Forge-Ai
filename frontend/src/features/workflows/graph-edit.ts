import type { Edge } from "@xyflow/react";
import type { GraphEdge, GraphNode } from "@/lib/api/types";
import { switchCases } from "./node-config";

export function serializeEdges(edges: Edge[]): GraphEdge[] {
  return edges.map((edge) => ({
    id: edge.id,
    source: edge.source,
    source_port: edge.sourceHandle || "out",
    target: edge.target,
    target_port: "in",
    mappings: (edge.data?.mappings || []) as GraphEdge["mappings"],
  }));
}

/** Clean up only explicitly deleted case IDs; malformed advanced config remains visible to validation. */
export function edgesAfterConfigEdit(
  edges: Edge[],
  node: GraphNode,
  config: GraphNode["config"],
): Edge[] {
  if (node.type !== "switch" || !Array.isArray(config.cases)) return edges;
  const cases = switchCases(config);
  if (!cases.length || cases.length !== config.cases.length) return edges;
  const remaining = new Set(cases.map((item) => item.id));
  const deleted = new Set(
    switchCases(node.config)
      .filter((item) => !remaining.has(item.id))
      .map((item) => item.id),
  );
  return edges.filter(
    (edge) =>
      edge.source !== node.id || !deleted.has(edge.sourceHandle || "out"),
  );
}

export function connectInsertedNode(
  edges: Edge[],
  sourceId: string,
  nodeId: string,
  outgoing: Edge | undefined,
  newEdgeId: string,
): Edge[] {
  if (!outgoing) {
    return [
      ...edges,
      {
        id: newEdgeId,
        source: sourceId,
        target: nodeId,
        sourceHandle: "out",
        targetHandle: "in",
        type: "smoothstep",
        data: { mappings: [] },
      },
    ];
  }
  return [
    ...edges.map((edge) =>
      edge.id === outgoing.id ? { ...edge, target: nodeId } : edge,
    ),
    {
      id: newEdgeId,
      source: nodeId,
      target: outgoing.target,
      sourceHandle: "out",
      targetHandle: "in",
      type: "smoothstep",
      data: { mappings: [] },
    },
  ];
}
