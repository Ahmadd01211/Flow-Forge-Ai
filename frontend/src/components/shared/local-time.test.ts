import { createElement } from "react";
import { renderToString } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { LocalTime, utcTimeLabel } from "./local-time";

describe("dates across server and browser time zones", () => {
  it("uses an explicit UTC representation for the hydration snapshot", () => {
    const html = renderToString(createElement(LocalTime, { value: "2026-10-25T00:41:22+05:00" }));
    expect(html).toContain("2026-10-24 19:41:22 UTC");
    expect(html).toMatch(/datetime="2026-10-25T00:41:22\+05:00"/i);
  });
  it("handles invalid timestamps without breaking the execution list", () => {
    expect(utcTimeLabel("unavailable")).toBe("Time unavailable");
  });
});
