/** Helpers that turn a tool's JSON Schema into readable fields and a starting argument object. */
type Schema = {
  type?: string | string[];
  description?: string;
  enum?: unknown[];
  const?: unknown;
  minimum?: number;
  properties?: Record<string, Schema>;
  required?: string[];
  items?: Schema;
  anyOf?: Schema[];
  oneOf?: Schema[];
};

export interface ToolField {
  name: string;
  type: string;
  required: boolean;
  description: string;
}

function typeLabel(schema: Schema): string {
  if (schema.enum) return schema.enum.map((value) => JSON.stringify(value)).join(" | ");
  const options = schema.anyOf || schema.oneOf;
  if (options) return options.map(typeLabel).join(" or ");
  const type = Array.isArray(schema.type) ? schema.type.join(" or ") : schema.type || "any";
  return type === "array" && schema.items ? `array of ${typeLabel(schema.items)}` : type;
}

export function toolFields(schema: unknown): ToolField[] {
  const root = (schema || {}) as Schema;
  const required = new Set(root.required || []);
  return Object.entries(root.properties || {})
    .map(([name, child]) => ({
      name,
      type: typeLabel(child),
      required: required.has(name),
      description: child.description || "",
    }))
    .sort((a, b) => Number(b.required) - Number(a.required) || a.name.localeCompare(b.name));
}

function placeholder(schema: Schema): unknown {
  if (schema.const !== undefined) return schema.const;
  if (schema.enum?.length) return schema.enum[0];
  const option = (schema.anyOf || schema.oneOf)?.[0];
  if (option) return placeholder(option);
  const type = Array.isArray(schema.type) ? schema.type[0] : schema.type;
  if (type === "number" || type === "integer") return schema.minimum ?? 1;
  if (type === "boolean") return false;
  if (type === "array") return [];
  if (type === "object") return exampleArguments(schema);
  return "";
}

/** Required fields only, with type-appropriate placeholders the user then edits. */
export function exampleArguments(schema: unknown): Record<string, unknown> {
  const root = (schema || {}) as Schema;
  return Object.fromEntries(
    (root.required || []).map((name) => [name, placeholder(root.properties?.[name] || {})]),
  );
}
