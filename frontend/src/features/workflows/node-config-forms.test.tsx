// @vitest-environment jsdom
import { useState } from "react";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import type { GraphNode } from "@/lib/api/types";
import { NodeConfigForm, type FormContext } from "./node-config-forms";

const context: FormContext = {
  workflowOptions: [],
  refreshWorkflows: () => {},
  loadingWorkflows: false,
  workspaceId: "w",
  workflowId: "flow",
  nodes: [],
  upstream: [],
  inputHints: ["/items"],
  agentOptions: [],
  mcpOptions: [],
  toolOptions: [],
  connections: [],
  skillOptions: [],
  httpOptions: [],
};
function Editor({
  type = "switch",
  config = {
    value: { kind: "input", pointer: "/priority" },
    cases: [
      { id: "urgent", label: "Urgent", value: true },
      { id: "normal", label: "Normal", value: 1 },
    ],
  },
}: {
  type?: string;
  config?: Record<string, unknown>;
}) {
  const [value, setValue] = useState(config);
  return (
    <>
      <NodeConfigForm
        node={
          {
            id: "route",
            type,
            config: value,
            label: "Route",
            join: "all",
            position: { x: 0, y: 0 },
            policy: {},
          } as GraphNode
        }
        context={context}
        issues={[
          {
            code: "NODE_CONFIG_INVALID",
            path: "config.cases.0.value",
            message: "Values must be unique",
            severity: "error",
          },
        ]}
        onChange={setValue}
      />
      <output data-testid="config">{JSON.stringify(value)}</output>
    </>
  );
}
const saved = () =>
  JSON.parse(screen.getByTestId("config").textContent || "{}");
afterEach(cleanup);

describe("Switch editor", () => {
  it("edits scalar values and labels, reorders and removes without changing IDs", () => {
    render(<Editor />);
    expect(screen.getByText("Default")).toBeTruthy();
    expect(screen.getByText("Values must be unique")).toBeTruthy();
    fireEvent.change(screen.getByLabelText("Case 1 label"), {
      target: { value: "High priority" },
    });
    fireEvent.change(screen.getByLabelText("Case 1 value type"), {
      target: { value: "text" },
    });
    fireEvent.change(screen.getByLabelText("Case 1 value"), {
      target: { value: "high" },
    });
    expect(saved().cases[0]).toEqual({
      id: "urgent",
      label: "High priority",
      value: "high",
    });
    expect(
      screen
        .getByLabelText("Case 1 value type")
        .querySelector('option[value="json"]'),
    ).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Move case 1 down" }));
    expect(saved().cases.map((c: { id: string }) => c.id)).toEqual([
      "normal",
      "urgent",
    ]);
    fireEvent.click(screen.getByRole("button", { name: "Remove case 1" }));
    expect(saved().cases.map((c: { id: string }) => c.id)).toEqual(["urgent"]);
    expect(
      (
        screen.getByRole("button", {
          name: "Remove case 1",
        }) as HTMLButtonElement
      ).disabled,
    ).toBe(true);
  });
  it("adds fresh stable IDs up to eight cases", () => {
    render(<Editor />);
    for (let i = 0; i < 6; i++)
      fireEvent.click(screen.getByRole("button", { name: "Add case" }));
    const cases = saved().cases;
    expect(cases).toHaveLength(8);
    expect(new Set(cases.map((c: { id: string }) => c.id)).size).toBe(8);
    expect(cases[0].id).toBe("urgent");
    expect(
      (screen.getByRole("button", { name: "Add case" }) as HTMLButtonElement)
        .disabled,
    ).toBe(true);
  });
});

describe("Remove duplicates editor", () => {
  it("saves source and optional object field and clears it for whole-item comparison", () => {
    render(<Editor type="list_deduplicate" config={{ source: "/items" }} />);
    fireEvent.change(screen.getByLabelText("List field path"), {
      target: { value: "/contacts" },
    });
    fireEvent.change(screen.getByLabelText("Item field path"), {
      target: { value: "/email" },
    });
    expect(saved()).toEqual({ source: "/contacts", item_pointer: "/email" });
    fireEvent.change(screen.getByLabelText("Item field path"), {
      target: { value: "" },
    });
    expect(saved()).toEqual({ source: "/contacts" });
    expect(screen.getByText(/first occurrence/i)).toBeTruthy();
  });
});
