// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { McpConnections, type McpServer } from "./mcp-connections";
vi.mock("@/lib/api/client", () => ({ api: vi.fn() }));
afterEach(cleanup);
function server(id: string, field: string): McpServer {
  return {
    id,
    name: id,
    source: "workspace",
    origin: "https://example.com",
    allowed_tools: ["lookup"],
    verified_tools: ["lookup"],
    runnable_tools: ["lookup"],
    runnable_schemas: {
      lookup: {
        type: "object",
        required: [field],
        properties: { [field]: { type: "string" } },
      },
    },
    tools: [{ name: "lookup", read_only: true, policy: "allow" }],
    policy_editable: true,
    state: "active",
    verified_at: null,
  };
}
it("starts the displayed tool with its required inputs and keeps edits scoped to each server", () => {
  render(
    <McpConnections
      workspaceId="ws"
      initial={{
        items: [server("First", "query"), server("Second", "repository")],
        workspace_servers: true,
      }}
      canManage
      canTest
    />,
  );
  expect(
    JSON.parse(
      (screen.getByLabelText("Arguments JSON") as HTMLTextAreaElement).value,
    ),
  ).toEqual({ query: "" });
  fireEvent.change(screen.getByLabelText("Arguments JSON"), {
    target: { value: '{"query":"saved"}' },
  });
  fireEvent.click(screen.getByRole("button", { name: /Second.*Connected/ }));
  expect(
    JSON.parse(
      (screen.getByLabelText("Arguments JSON") as HTMLTextAreaElement).value,
    ),
  ).toEqual({ repository: "" });
  fireEvent.click(screen.getByRole("button", { name: /First.*Connected/ }));
  expect(
    JSON.parse(
      (screen.getByLabelText("Arguments JSON") as HTMLTextAreaElement).value,
    ),
  ).toEqual({ query: "saved" });
});
it("explains missing required inputs before sending a tool test", () => {
  render(
    <McpConnections
      workspaceId="ws"
      initial={{ items: [server("First", "query")], workspace_servers: true }}
      canManage
      canTest
    />,
  );
  fireEvent.change(screen.getByLabelText("Arguments JSON"), {
    target: { value: "{}" },
  });
  expect(screen.getByRole("button", { name: "Run tool test" })).toHaveProperty(
    "disabled",
    true,
  );
  expect(screen.getByText("Add required inputs: query.")).toBeTruthy();
});
