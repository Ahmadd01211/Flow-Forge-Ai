"use client";

import { Plus, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import type { GraphEdge, ValidationIssue } from "@/lib/api/types";

export function DataMappings({
  incoming,
  names,
  issues,
  onChange,
  remember,
}: {
  incoming: GraphEdge[];
  names: Record<string, string>;
  issues: ValidationIssue[];
  onChange: (id: string, mappings: GraphEdge["mappings"]) => void;
  remember: () => void;
}) {
  if (!incoming.length) return null;
  return (
    <section className="node-data-mappings">
      <h3>Incoming field mappings</h3>
      <p>
        Map an earlier step&apos;s output into this step&apos;s input. Field
        paths use JSON Pointer, such as <code>/ticket/id</code>. Empty source
        selects the whole output; empty target replaces the whole input.
      </p>
      {incoming.map((edge) => (
        <details key={edge.id}>
          <summary>
            From {names[edge.source] || edge.source}
            {edge.source_port !== "out" && ` · ${edge.source_port}`}
          </summary>
          {issues
            .filter((issue) => issue.edge_id === edge.id)
            .map((issue, index) => (
              <p className="field-error" key={index}>
                {issue.message}
              </p>
            ))}
          {edge.mappings.length ? (
            edge.mappings.map((mapping, index) => (
              <div className="mapping-fields" key={index} onFocus={remember}>
                <label>
                  From output
                  <input
                    aria-label={`Source field ${index + 1} from ${names[edge.source] || edge.source}`}
                    value={mapping.from}
                    maxLength={512}
                    placeholder="Whole output"
                    onChange={(e) =>
                      onChange(
                        edge.id,
                        edge.mappings.map((item, i) =>
                          i === index
                            ? { ...item, from: e.target.value }
                            : item,
                        ),
                      )
                    }
                  />
                </label>
                <label>
                  To input
                  <input
                    aria-label={`Target field ${index + 1} from ${names[edge.source] || edge.source}`}
                    value={mapping.to}
                    maxLength={512}
                    placeholder="Whole input"
                    onChange={(e) =>
                      onChange(
                        edge.id,
                        edge.mappings.map((item, i) =>
                          i === index ? { ...item, to: e.target.value } : item,
                        ),
                      )
                    }
                  />
                </label>
                <Button
                  variant="ghost"
                  size="sm"
                  aria-label={`Remove mapping ${index + 1} from ${names[edge.source] || edge.source}`}
                  onClick={() => {
                    remember();
                    onChange(
                      edge.id,
                      edge.mappings.filter((_, i) => i !== index),
                    );
                  }}
                >
                  <Trash2 size={13} />
                </Button>
              </div>
            ))
          ) : (
            <p>Full output passes through.</p>
          )}
          <Button
            variant="outline"
            size="sm"
            disabled={edge.mappings.length >= 64}
            onClick={() => {
              remember();
              onChange(edge.id, [
                ...edge.mappings,
                { from: "", to: `/field_${edge.mappings.length + 1}` },
              ]);
            }}
          >
            <Plus size={13} />
            Add field mapping
          </Button>
        </details>
      ))}
      {incoming.length > 1 && (
        <p>
          When several paths are active, their mapped values are grouped under
          their source step IDs. The step waits until every incoming path is
          resolved.
        </p>
      )}
    </section>
  );
}
