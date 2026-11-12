// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { HttpToolRegistry } from "./http-tool-registry";
const { request } = vi.hoisted(() => ({ request: vi.fn() }));
vi.mock("@/lib/api/client", () => ({ api: request }));
afterEach(() => {
  cleanup();
  request.mockReset();
});
function setup() {
  request.mockRejectedValue(new Error("Backend validation required."));
  render(
    <HttpToolRegistry workspaceId="ws" initialTools={[]} canManage canTest />,
  );
  fireEvent.click(screen.getByRole("button", { name: "Add API tool" }));
  fireEvent.change(screen.getByLabelText("Tool name"), {
    target: { value: "Lookup" },
  });
  fireEvent.click(
    screen.getByLabelText(
      "I approve this destination, method and access for this workspace.",
    ),
  );
}
it("explains a non-HTTPS endpoint before attempting approval", async () => {
  setup();
  fireEvent.change(screen.getByLabelText("Fixed HTTPS endpoint"), {
    target: { value: "http://example.com" },
  });
  fireEvent.submit(
    screen.getByRole("button", { name: "Approve tool" }).closest("form")!,
  );
  expect(await screen.findByRole("alert")).toHaveProperty(
    "textContent",
    "Use a public HTTPS endpoint on port 443.",
  );
  expect(request).not.toHaveBeenCalled();
});
it("names the invalid JSON contract and keeps the draft for correction", async () => {
  setup();
  fireEvent.change(screen.getByLabelText("Fixed HTTPS endpoint"), {
    target: { value: "https://example.com" },
  });
  fireEvent.change(screen.getByLabelText("Input JSON Schema"), {
    target: { value: "{" },
  });
  fireEvent.submit(
    screen.getByRole("button", { name: "Approve tool" }).closest("form")!,
  );
  expect(await screen.findByRole("alert")).toHaveProperty(
    "textContent",
    "Input schema must contain valid JSON.",
  );
  expect(screen.getByLabelText("Input JSON Schema")).toHaveProperty(
    "value",
    "{",
  );
  expect(request).not.toHaveBeenCalled();
});
