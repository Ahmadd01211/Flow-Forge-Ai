// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import type { Connection } from "@/lib/api/types";
import { ProviderConnection } from "./provider-connection";
const { request, refresh } = vi.hoisted(() => ({
  request: vi.fn(),
  refresh: vi.fn(),
}));
vi.mock("@/lib/api/client", () => ({ api: request }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh }) }));
const capability = (runnable: boolean) => ({
  runnable,
  reason: runnable ? "Ready" : "Setup only",
  input_usd_per_million: "1",
  output_usd_per_million: "2",
  local_tools: false,
  structured_output: false,
});
const connection = {
  id: "connection",
  workspace_id: "ws",
  provider: "openai",
  display_name: "OpenAI",
  state: "active",
  credential_generation: 1,
  masked_hint: "••••aaaa",
  verified_models: ["ready-model", "setup-model"],
  default_model_id: null,
  verified_at: "2026-01-01T00:00:00Z",
  revoked_at: null,
  model_capabilities: {
    "ready-model": capability(true),
    "setup-model": capability(false),
  },
} as Connection;
function setup(connections: Connection[] = []) {
  render(
    <ProviderConnection workspaceId="ws" connections={connections} canManage />,
  );
}
beforeEach(() => {
  request.mockReset();
  refresh.mockReset();
});
afterEach(cleanup);
it("distinguishes setup-only models from search misses", () => {
  setup([
    {
      ...connection,
      verified_models: ["setup-model"],
      model_capabilities: { "setup-model": capability(false) },
    } as Connection,
  ]);
  expect(screen.getByText(/no runnable models/i)).toBeTruthy();
  expect(screen.queryByText(/no models match that search/i)).toBeNull();
  fireEvent.click(screen.getByLabelText(/show models for setup only/i));
  expect(screen.getByRole("button", { name: /setup-model/ })).toBeTruthy();
  fireEvent.change(screen.getByLabelText("Search available models"), {
    target: { value: "missing" },
  });
  expect(screen.getByText(/no models match that search/i)).toBeTruthy();
});
it("verifies a key and saves a selected model", async () => {
  request
    .mockResolvedValueOnce(connection)
    .mockResolvedValueOnce({ ...connection, default_model_id: "ready-model" });
  setup();
  fireEvent.change(screen.getByLabelText("OpenAI API key"), {
    target: { value: "test-secret" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Verify key" }));
  fireEvent.click(await screen.findByRole("button", { name: /ready-model/ }));
  fireEvent.click(screen.getByRole("button", { name: "Save default model" }));
  expect(await screen.findByText(/is now the default/i)).toBeTruthy();
  expect(request).toHaveBeenLastCalledWith(
    "/workspaces/ws/integrations/providers/openai/default-model",
    { method: "PATCH", body: JSON.stringify({ model_id: "ready-model" }) },
  );
  expect(screen.getByLabelText("OpenAI API key")).toHaveProperty("value", "");
});
it("shows rejected credentials without echoing the key and clears both on provider switch", async () => {
  request.mockRejectedValueOnce(
    new Error("The provider rejected this credential."),
  );
  setup();
  fireEvent.change(screen.getByLabelText("OpenAI API key"), {
    target: { value: "test-secret" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Verify key" }));
  expect((await screen.findByRole("alert")).textContent).not.toContain(
    "test-secret",
  );
  fireEvent.change(screen.getByLabelText("Model provider"), {
    target: { value: "deepseek" },
  });
  expect(screen.queryByRole("alert")).toBeNull();
  expect(screen.getByLabelText("DeepSeek API key")).toHaveProperty("value", "");
});
it("keeps the displayed catalog and default after a failed refresh", async () => {
  request.mockRejectedValueOnce(
    new Error("Provider verification is unavailable."),
  );
  setup([{ ...connection, default_model_id: "ready-model" }]);
  fireEvent.click(screen.getByRole("button", { name: "Refresh models" }));
  expect(await screen.findByRole("alert")).toHaveProperty(
    "textContent",
    "Provider verification is unavailable.",
  );
  expect(
    screen.getByRole("button", { name: /ready-model.*current default/i }),
  ).toBeTruthy();
});
