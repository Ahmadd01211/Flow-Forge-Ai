import { describe, expect, it } from "vitest";
import { exampleArguments, toolFields } from "./mcp-schema";

const searchCode = {
  type: "object",
  required: ["query"],
  properties: {
    query: { type: "string", description: "Search query" },
    perPage: { type: "number", minimum: 1, maximum: 100 },
    order: { type: "string", enum: ["asc", "desc"] },
    fields: { type: "array", items: { type: "string", enum: ["name", "path"] } },
    repoName: { anyOf: [{ type: "string" }, { type: "array", items: { type: "string" } }] },
  },
};

describe("MCP tool schema helpers", () => {
  it("lists required fields first with readable types", () => {
    expect(toolFields(searchCode).map((field) => [field.name, field.type, field.required])).toEqual([
      ["query", "string", true],
      ["fields", 'array of "name" | "path"', false],
      ["order", '"asc" | "desc"', false],
      ["perPage", "number", false],
      ["repoName", "string or array of string", false],
    ]);
  });

  it("builds a starting object from required fields only", () => {
    expect(exampleArguments(searchCode)).toEqual({ query: "" });
    expect(exampleArguments({ required: ["n", "mode"], properties: { n: { type: "integer", minimum: 2 }, mode: { enum: ["a"] } } })).toEqual({ n: 2, mode: "a" });
    expect(exampleArguments(undefined)).toEqual({});
  });
});
