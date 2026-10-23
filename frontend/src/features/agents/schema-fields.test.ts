import { describe, expect, it } from "vitest";
import { readFields, writeFields } from "./schema-fields";
describe("guided schema editing", () => {
  const schema = JSON.stringify({
    type: "object",
    description: "Ticket",
    properties: {
      priority: {
        type: "string",
        enum: ["urgent", "normal"],
        description: "Impact",
      },
    },
    required: ["priority"],
    additionalProperties: false,
  });
  it("preserves enums and root metadata while adding a field", () => {
    const fields = readFields(schema)!;
    const result = JSON.parse(
      writeFields(schema, [
        ...fields,
        {
          name: "reason",
          type: "string",
          description: "Explain why",
          required: true,
        },
      ]),
    );
    expect(result.description).toBe("Ticket");
    expect(result.properties.priority.enum).toEqual(["urgent", "normal"]);
    expect(result.required).toEqual(["priority", "reason"]);
    expect(result.additionalProperties).toBe(false);
  });
  it("refuses to simplify nested or constrained schemas", () => {
    expect(
      readFields(
        JSON.stringify({
          type: "object",
          properties: { customer: { type: "object", properties: {} } },
          required: [],
          additionalProperties: false,
        }),
      ),
    ).toBeNull();
    expect(
      readFields(
        schema.replace('"type":"string"', '"type":"string","maxLength":50'),
      ),
    ).toBeNull();
    expect(readFields("{bad-json")).toBeNull();
  });
  it("rejects duplicate or unsafe names without modifying the source", () => {
    const fields = readFields(schema)!;
    expect(() => writeFields(schema, [...fields, fields[0]])).toThrow();
    expect(() =>
      writeFields(schema, [{ ...fields[0], name: "__proto__" }]),
    ).toThrow();
    expect(readFields(schema)![0].name).toBe("priority");
  });
});
