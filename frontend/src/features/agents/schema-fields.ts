type Primitive = "string" | "number" | "integer" | "boolean";
export interface SchemaField {
  name: string;
  type: Primitive;
  description: string;
  required: boolean;
  enum?: unknown[];
}
const types = new Set(["string", "number", "integer", "boolean"]);

export function readFields(text: string): SchemaField[] | null {
  try {
    const root = JSON.parse(text);
    if (
      !root ||
      root.type !== "object" ||
      !root.properties ||
      typeof root.properties !== "object" ||
      Array.isArray(root.properties) ||
      root.additionalProperties !== false ||
      !Array.isArray(root.required) ||
      Object.keys(root).some(
        (k) =>
          ![
            "type",
            "properties",
            "required",
            "additionalProperties",
            "description",
          ].includes(k),
      )
    )
      return null;
    const fields: SchemaField[] = [];
    for (const [name, value] of Object.entries(root.properties)) {
      if (
        !/^[a-zA-Z][a-zA-Z0-9_]{0,63}$/.test(name) ||
        ["constructor", "prototype", "__proto__"].includes(name)
      )
        return null;
      const v = value as Record<string, unknown>;
      if (
        !v ||
        !types.has(String(v.type)) ||
        Object.keys(v).some(
          (k) => !["type", "description", "enum"].includes(k),
        ) ||
        (v.enum !== undefined &&
          (!Array.isArray(v.enum) ||
            v.type !== "string" ||
            v.enum.some((x) => typeof x !== "string")))
      )
        return null;
      fields.push({
        name,
        type: v.type as Primitive,
        description: typeof v.description === "string" ? v.description : "",
        required: root.required.includes(name),
        ...(v.enum ? { enum: v.enum as unknown[] } : {}),
      });
    }
    if (
      root.required.some(
        (name: string) => !Object.hasOwn(root.properties, name),
      )
    )
      return null;
    return fields;
  } catch {
    return null;
  }
}

export function writeFields(text: string, fields: SchemaField[]): string {
  if (
    fields.length > 32 ||
    new Set(fields.map((f) => f.name)).size !== fields.length ||
    fields.some(
      (f) =>
        !/^[a-zA-Z][a-zA-Z0-9_]{0,63}$/.test(f.name) ||
        ["constructor", "prototype", "__proto__"].includes(f.name),
    )
  )
    throw new Error(
      "Use unique field names beginning with a letter, with up to 64 letters, digits or underscores.",
    );
  return JSON.stringify(
    {
      ...JSON.parse(text),
      properties: Object.fromEntries(
        fields.map((f) => [
          f.name,
          {
            type: f.type,
            ...(f.description ? { description: f.description } : {}),
            ...(f.enum ? { enum: f.enum } : {}),
          },
        ]),
      ),
      required: fields.filter((f) => f.required).map((f) => f.name),
    },
    null,
    2,
  );
}
