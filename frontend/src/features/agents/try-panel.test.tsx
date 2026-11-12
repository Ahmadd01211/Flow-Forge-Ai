// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { TryPanel } from "./try-panel";
import { CHAT_INPUT, REPLY_OUTPUT } from "./builder-model";
import type { AgentConfig } from "@/lib/api/types";
const defaultConfig: AgentConfig = {
  schema_version: 1,
  instructions: "",
  provider: "openai",
  model_id: "",
  tool_keys: [],
  mcp_tools: [],
  http_tools: [],
  memory: null,
  workflow_tools: [],
  skills: [],
  skill_loading: "on_demand",
  input_schema: CHAT_INPUT,
  output_schema: REPLY_OUTPUT,
  limits: {
    max_iterations: 8,
    timeout_seconds: 60,
    max_cost_usd: "0.10",
    max_tool_calls: 8,
    max_output_tokens: 4096,
  },
};
const { request } = vi.hoisted(() => ({ request: vi.fn() }));
vi.mock("@/lib/api/client", () => ({ api: request }));
beforeEach(() => {
  request.mockReset();
  Element.prototype.scrollIntoView = vi.fn();
});
afterEach(cleanup);
describe("recipe agent sample", () => {
  it("initializes fields once, preserves user edits and never auto-runs", () => {
    const config = {
      ...defaultConfig,
      input_schema: {
        type: "object",
        properties: { customer_message: { type: "string" } },
        required: ["customer_message"],
        additionalProperties: false,
      },
    };
    const props = {
      workspaceId: "ws",
      agentId: "agent",
      config,
      schemasValid: true,
      canEdit: true,
    };
    const view = render(
      <TryPanel
        {...props}
        recipeSample={{
          sampleInput: { customer_message: "Where is my order?" },
          expectedResult: "Ask for an order number.",
        }}
      />,
    );
    expect(screen.getByDisplayValue("Where is my order?")).toBeTruthy();
    expect(
      screen.getByText("Expected example: Ask for an order number."),
    ).toBeTruthy();
    fireEvent.change(screen.getByDisplayValue("Where is my order?"), {
      target: { value: "My own safe input" },
    });
    view.rerender(
      <TryPanel
        {...props}
        recipeSample={{ sampleInput: { customer_message: "New example" } }}
      />,
    );
    expect(screen.getByDisplayValue("My own safe input")).toBeTruthy();
    expect(request).not.toHaveBeenCalled();
  });
  it("initializes chat input and leaves sample-free recipes blank", () => {
    const props = {
      workspaceId: "ws",
      agentId: "agent",
      config: defaultConfig,
      schemasValid: true,
      canEdit: true,
    };
    const view = render(
      <TryPanel
        {...props}
        recipeSample={{ sampleInput: { message: "Hello from recipe" } }}
      />,
    );
    expect(screen.getByDisplayValue("Hello from recipe")).toBeTruthy();
    view.unmount();
    render(<TryPanel {...props} recipeSample={{}} />);
    expect(
      (screen.getByLabelText("Message") as HTMLTextAreaElement).value,
    ).toBe("");
    expect(screen.getByText(/enter your own safe sample/i)).toBeTruthy();
    expect(request).not.toHaveBeenCalled();
  });
});
