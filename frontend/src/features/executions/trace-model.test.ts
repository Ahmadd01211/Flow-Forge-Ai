import { describe, expect, it } from "vitest";
import { ms, usd, waterfall, type TraceStep } from "./trace-model";

const step = (start: string | null, end: string): TraceStep => ({
  kind: "tool", label: "t", status: "completed", error_code: null, started_at: start, finished_at: end,
  duration_ms: null, input_tokens: null, output_tokens: null, cost_usd: null, arguments: null, output: null,
});

describe("trace helpers", () => {
  it("places each step on the run's timeline", () => {
    const bars = waterfall(
      [step("2026-11-02T00:00:00Z", "2026-11-02T00:00:01Z"), step("2026-11-02T00:00:02Z", "2026-11-02T00:00:04Z")],
      "2026-11-02T00:00:00Z", "2026-11-02T00:00:04Z",
    );
    expect(bars).toEqual([{ left: 0, width: 25 }, { left: 50, width: 50 }]);
    expect(waterfall([step(null, "2026-11-02T00:00:04Z")], "2026-11-02T00:00:00Z", "2026-11-02T00:00:04Z")[0].width).toBe(1.5);
  });

  it("formats durations and money", () => {
    expect(ms(null)).toBe("—");
    expect(ms(420)).toBe("420 ms");
    expect(ms(2500)).toBe("2.5 s");
    expect(ms(42000)).toBe("42 s");
    expect(usd("0.00123")).toBe("$0.0012");
    expect(usd(null)).toBe("—");
  });
});
