// @vitest-environment jsdom
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
} from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { AgentEditor } from "./agent-editor";
import { TryPanel } from "./try-panel";
import type { Agent, AgentConfig } from "@/lib/api/types";
const { mockApi } = vi.hoisted(() => ({ mockApi: vi.fn() }));
vi.mock("@/lib/api/client", () => ({ api: mockApi }));
vi.mock("next/navigation", () => ({
  useRouter: () => ({ refresh: vi.fn(), replace: vi.fn() }),
}));
vi.mock("@/lib/use-unsaved-changes", () => ({ useUnsavedChanges: vi.fn() }));
vi.mock("./performance-block", () => ({ PerformanceBlock: () => null }));
vi.mock("@/features/templates/save-template", () => ({
  SaveTemplate: () => null,
}));
vi.mock("@/features/executions/feedback", () => ({
  FeedbackButtons: () => null,
}));
const config = {
  schema_version: 1,
  instructions: "Help",
  provider: "openai",
  model_id: "test",
  tool_keys: [],
  mcp_tools: [],
  http_tools: [],
  workflow_tools: [],
  skills: [],
  skill_loading: "on_demand",
  memory: null,
  input_schema: { type: "object", properties: { message: { type: "string" } } },
  output_schema: { type: "object" },
  limits: {
    max_iterations: 8,
    timeout_seconds: 60,
    max_cost_usd: "0.1",
    max_tool_calls: 8,
    max_output_tokens: 100,
  },
} as AgentConfig;
const agent = {
  id: "a",
  name: "Helper",
  description: "",
  revision: 1,
  config,
} as Agent;
const ready = { errors: [], warnings: [], runnable: true };
function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((r) => {
    resolve = r;
  });
  return { promise, resolve };
}
beforeEach(() => {
  mockApi.mockReset();
  Element.prototype.scrollIntoView = vi.fn();
});
afterEach(cleanup);
it.each(["status", "events"])(
  "keeps accepted run identity as unknown when %s polling fails",
  async (failedRequest) => {
    vi.useFakeTimers();
    try {
      const onSampleEvent = vi.fn();
      mockApi.mockImplementation((path: string) => {
        if (path.endsWith("/try"))
          return Promise.resolve({
            run: { id: "accepted-run", state: "running" },
          });
        const isEvents = path.endsWith("/events");
        return isEvents === (failedRequest === "events")
          ? Promise.reject(new Error("Connection lost"))
          : Promise.resolve(
              isEvents
                ? { items: [] }
                : { id: "accepted-run", state: "running" },
            );
      });
      render(
        <TryPanel
          workspaceId="w"
          agentId="a"
          config={config}
          schemasValid
          canEdit
          onSampleEvent={onSampleEvent}
        />,
      );
      fireEvent.change(screen.getByLabelText("Message"), {
        target: { value: "hello" },
      });
      fireEvent.click(screen.getByRole("button", { name: "Send" }));
      await act(async () => {});
      await act(async () => vi.advanceTimersByTimeAsync(1000));
      expect(onSampleEvent.mock.calls.at(-1)?.[0]).toMatchObject({
        ...onSampleEvent.mock.calls[0][0],
        state: "unknown",
        runId: "accepted-run",
      });
      expect(
        screen
          .getByRole("link", { name: /See what happened/ })
          .getAttribute("href"),
      ).toBe("/w/w/executions/accepted-run");
    } finally {
      vi.useRealTimers();
    }
  },
);
const check = async () => {
  fireEvent.click(screen.getByRole("button", { name: "Check setup" }));
  await act(async () => {});
};
it("offers save for unsaved agents without launching", () => {
  render(<AgentEditor workspaceId="w" />);
  fireEvent.click(screen.getByRole("button", { name: "Save your draft" }));
  expect(mockApi).not.toHaveBeenCalled();
});
it.each([
  ["model", "Provider missing", "block-brain"],
  ["skills", "Skill unpublished", "block-skills"],
  ["future", "Unknown server issue", "publish-diagnostics"],
])("reveals %s diagnostics without a run", async (section, message, id) => {
  mockApi.mockResolvedValue({
    ...ready,
    errors: [{ code: "problem", section, message }],
  });
  render(<AgentEditor agent={agent} workspaceId="w" />);
  await check();
  fireEvent.click(
    screen.getByRole("button", { name: `Review issue: ${message}` }),
  );
  expect(document.getElementById(id)).toBeTruthy();
  expect(mockApi.mock.calls.every(([path]) => !path.endsWith("/try"))).toBe(
    true,
  );
});
it("supports setup-only, failed checks and viewers", async () => {
  mockApi.mockResolvedValue({ ...ready, runnable: false });
  const view = render(<AgentEditor agent={agent} workspaceId="w" />);
  await check();
  expect(
    screen.getByText("This model is setup only and cannot run samples."),
  ).toBeTruthy();
  expect(
    screen.getByRole("button", { name: "Publish a version" }),
  ).toBeTruthy();
  view.unmount();
  mockApi.mockRejectedValue(new Error("Offline"));
  render(<AgentEditor agent={agent} workspaceId="w" />);
  await check();
  expect(
    screen.getByText("Setup check could not be completed. Try again."),
  ).toBeTruthy();
  cleanup();
  render(<AgentEditor agent={agent} workspaceId="w" canEdit={false} />);
  expect(
    (screen.getByRole("button", { name: "Check setup" }) as HTMLButtonElement)
      .disabled,
  ).toBe(true);
});
it("ignores readiness returned after an edit", async () => {
  const pending = deferred<typeof ready>();
  mockApi.mockReturnValue(pending.promise);
  render(<AgentEditor agent={agent} workspaceId="w" />);
  await check();
  fireEvent.change(screen.getByLabelText("Agent name"), {
    target: { value: "Changed" },
  });
  await act(async () => pending.resolve(ready));
  expect(screen.queryByText("Setup checked.")).toBeNull();
});
it("captures submitted unsaved configuration and evidence before awaiting", async () => {
  const pending = deferred<unknown>();
  mockApi.mockReturnValue(pending.promise);
  const onSampleEvent = vi.fn();
  const props = {
    workspaceId: "w",
    agentId: "a",
    config,
    schemasValid: true,
    canEdit: true,
    onSampleEvent,
  };
  const view = render(<TryPanel {...props} />);
  fireEvent.change(screen.getByLabelText("Message"), {
    target: { value: "hello" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Send" }));
  expect(onSampleEvent.mock.calls[0][0].state).toBe("running");
  const start = onSampleEvent.mock.calls[0][0];
  expect(JSON.parse(mockApi.mock.calls[0][1].body)).toEqual({
    config,
    input: { message: "hello" },
  });
  view.rerender(
    <TryPanel {...props} config={{ ...config, instructions: "Changed" }} />,
  );
  await act(async () =>
    pending.resolve({
      run: {
        id: "r",
        state: "completed",
        output: { reply: "historical answer" },
      },
    }),
  );
  expect(onSampleEvent.mock.calls[1][0]).toMatchObject({
    ...start,
    state: "completed",
    runId: "r",
  });
});
it("clears completion on tab return and rechecking cannot restore it", async () => {
  mockApi.mockImplementation((path: string) =>
    Promise.resolve(
      path.endsWith("/try")
        ? {
            run: {
              id: "r",
              state: "completed",
              output: { reply: "historical answer" },
            },
          }
        : ready,
    ),
  );
  render(<AgentEditor agent={agent} workspaceId="w" />);
  await check();
  fireEvent.change(screen.getByLabelText("Message"), {
    target: { value: "hello" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Send" }));
  await act(async () => {});
  expect(screen.getByText("Sample succeeded")).toBeTruthy();
  Object.defineProperty(document, "visibilityState", {
    configurable: true,
    value: "hidden",
  });
  fireEvent(document, new Event("visibilitychange"));
  Object.defineProperty(document, "visibilityState", {
    configurable: true,
    value: "visible",
  });
  fireEvent(document, new Event("visibilitychange"));
  await check();
  expect(screen.queryByText("Sample succeeded")).toBeNull();
  expect(screen.getByText("historical answer")).toBeTruthy();
});
it.each(["completed", "failed"])(
  "keeps the latest %s attempt when older success arrives late",
  async (state) => {
    const first = deferred<unknown>(),
      second = deferred<unknown>();
    let attempts = 0;
    mockApi.mockImplementation((path: string) =>
      path.endsWith("/try")
        ? ++attempts === 1
          ? first.promise
          : second.promise
        : Promise.resolve(ready),
    );
    render(<AgentEditor agent={agent} workspaceId="w" />);
    await check();
    const message = screen.getByLabelText("Message");
    fireEvent.change(message, { target: { value: "first" } });
    fireEvent.submit(message.closest("form")!);
    fireEvent.change(message, { target: { value: "second" } });
    fireEvent.submit(message.closest("form")!);
    await act(async () =>
      second.resolve({
        run: { id: "second", state, output: { reply: "second response" } },
      }),
    );
    await act(async () =>
      first.resolve({
        run: {
          id: "first",
          state: "completed",
          output: { reply: "old response" },
        },
      }),
    );
    expect(
      screen.getByText(
        state === "completed" ? "Sample succeeded" : "Sample failed",
      ),
    ).toBeTruthy();
    if (state === "failed")
      expect(screen.queryByText("Sample succeeded")).toBeNull();
  },
);
it("an edit during a sample keeps its historical output without current success", async () => {
  const pending = deferred<unknown>();
  mockApi.mockImplementation((path: string) =>
    path.endsWith("/try") ? pending.promise : Promise.resolve(ready),
  );
  render(<AgentEditor agent={agent} workspaceId="w" />);
  await check();
  fireEvent.change(screen.getByLabelText("Message"), {
    target: { value: "hello" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Send" }));
  fireEvent.change(screen.getByLabelText("Agent name"), {
    target: { value: "Changed" },
  });
  await act(async () =>
    pending.resolve({
      run: { id: "r", state: "completed", output: { reply: "old output" } },
    }),
  );
  expect(screen.queryByText("Sample succeeded")).toBeNull();
  expect(screen.getByText("old output")).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "Check setup" }));
  expect(
    mockApi.mock.calls.filter(([path]) => path.endsWith("/readiness")),
  ).toHaveLength(1);
});
it("shares the pending readiness request with publish", async () => {
  const pending = deferred<typeof ready>();
  mockApi.mockReturnValue(pending.promise);
  render(<AgentEditor agent={agent} workspaceId="w" />);
  await check();
  fireEvent.click(screen.getByRole("button", { name: "Publish" }));
  expect(mockApi).toHaveBeenCalledTimes(1);
  await act(async () => pending.resolve(ready));
  expect(
    screen.getByText("Everything checks out. Ready to publish."),
  ).toBeTruthy();
});
it("reports observed approval waiting before polling finishes", async () => {
  vi.useFakeTimers();
  const onSampleEvent = vi.fn();
  mockApi.mockImplementation((path: string) =>
    Promise.resolve(
      path.endsWith("/try")
        ? { run: { id: "r", state: "waiting" } }
        : path.endsWith("/events")
          ? { items: [] }
          : { id: "r", state: "completed", output: { reply: "done" } },
    ),
  );
  render(
    <TryPanel
      workspaceId="w"
      agentId="a"
      config={config}
      schemasValid
      canEdit
      onSampleEvent={onSampleEvent}
    />,
  );
  fireEvent.change(screen.getByLabelText("Message"), {
    target: { value: "hello" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Send" }));
  await act(async () => {});
  expect(onSampleEvent.mock.calls.map(([event]) => event.state)).toContain(
    "waiting",
  );
  await act(async () => vi.advanceTimersByTimeAsync(1000));
  vi.useRealTimers();
});
