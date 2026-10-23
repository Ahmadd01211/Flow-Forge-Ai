import { describe, expect, it } from "vitest";
import { authSchema } from "./validation";
const loginSchema = authSchema("login"),
  registerSchema = authSchema("register");
describe("authentication input", () => {
  it("does not apply new-password rules to existing-account login", () => {
    expect(
      loginSchema.safeParse({ email: "alex@example.com", password: "existing" })
        .success,
    ).toBe(true);
    expect(
      registerSchema.safeParse({
        email: "alex@example.com",
        password: "existing",
        name: "Alex",
        workspace_name: "Acme",
      }).success,
    ).toBe(false);
  });
  it("rejects blank workspace identities and malformed email", () => {
    expect(
      registerSchema.safeParse({
        email: "alex@example.com",
        password: "unique-password-here",
        name: "  ",
        workspace_name: "Acme",
      }).success,
    ).toBe(false);
    expect(
      loginSchema.safeParse({ email: "not-an-email", password: "pass" })
        .success,
    ).toBe(false);
  });
  it("normalizes surrounding display-name whitespace", () => {
    expect(
      registerSchema.parse({
        email: "alex@example.com",
        password: "unique-password-here",
        name: " Alex ",
        workspace_name: " Acme ",
      }).workspace_name,
    ).toBe("Acme");
  });
});
