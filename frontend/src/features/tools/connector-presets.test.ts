import { describe, expect, it } from "vitest";
import { connectorPreset } from "./connector-presets";

describe("guided connector permission recipes", () => {
  it("pins GitHub repository paths and least-privilege contracts", () => {
    const read = connectorPreset("github-read", "acme", "operations", "");
    expect(read.url).toBe(
      "https://api.github.com/repos/acme/operations/issues",
    );
    expect(read.method).toBe("GET");
    expect(read.readOnly).toBe(true);
    expect(read.inputSchema.required).toEqual(["per_page"]);
    expect(
      connectorPreset("github-issue", "acme", "operations", "").method,
    ).toBe("POST");
    for (const repository of [
      "../private",
      "x?token=secret",
      "..",
      "x/#outside",
      "",
    ])
      expect(() =>
        connectorPreset("github-read", "acme", repository, ""),
      ).toThrow();
    expect(() =>
      connectorPreset("github-issue", "acme.evil/path", "operations", ""),
    ).toThrow();
  });
  it("pins the Slack channel and requires a confirmed success response", () => {
    const preset = connectorPreset("slack-message", "", "", "C0123456789");
    expect(preset.url).toBe("https://slack.com/api/chat.postMessage");
    expect(preset.inputSchema.properties).toMatchObject({
      channel: { const: "C0123456789" },
      mrkdwn: { const: false },
    });
    expect(preset.outputSchema.properties.body).toMatchObject({
      properties: { ok: { const: true }, channel: { const: "C0123456789" } },
    });
    expect(() =>
      connectorPreset("slack-message", "", "", "#anything"),
    ).toThrow();
  });
});
