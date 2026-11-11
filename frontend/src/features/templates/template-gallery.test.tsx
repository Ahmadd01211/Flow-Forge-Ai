// @vitest-environment jsdom
import {
  cleanup,
  fireEvent,
  render,
  screen,
  within,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { TemplateGallery, type TemplateEntry } from "./template-gallery";
import { TaskStart } from "../workspace/task-start";

const { request, push } = vi.hoisted(() => ({
  request: vi.fn(),
  push: vi.fn(),
}));
vi.mock("@/lib/api/client", () => ({ api: request }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ push }) }));

const agent: TemplateEntry = {
  key: "faq-answer",
  name: "Answer questions",
  description: "Use supplied references",
  category: "Knowledge",
  kind: "agent",
  template_version: 1,
};
const workflow: TemplateEntry = {
  key: "local",
  name: "Format a report",
  description: "Arrange text",
  category: "Productivity",
  kind: "workflow",
  template_version: 1,
};
const agentDetail = {
  ...agent,
  config: { instructions: "Answer from references." },
  setup_steps: ["Connect a provider."],
  sample_input: { question: "When?" },
  expected_result: "An answer grounded in references.",
  starter_skills: ["plain-language", "summarise-sources"],
};

beforeEach(() => {
  request.mockReset();
  push.mockReset();
});
afterEach(cleanup);
function gallery(canCreate = true) {
  return render(
    <TemplateGallery
      workspaceId="ws-1"
      templates={[agent, workflow]}
      canCreate={canCreate}
    />,
  );
}

describe("guided recipes", () => {
  it("recommends a natural-language task or selected category without a focus URL", () => {
    gallery();
    fireEvent.change(screen.getByLabelText("Search recipes"), {
      target: { value: "I want to answer customer questions" },
    });
    let recommended = screen.getByText("Recommended").closest("article")!;
    expect(
      within(recommended).getByRole("heading", { name: agent.name }),
    ).toBeTruthy();
    fireEvent.change(screen.getByLabelText("Search recipes"), {
      target: { value: "" },
    });
    fireEvent.change(screen.getByLabelText("Category"), {
      target: { value: "Productivity" },
    });
    recommended = screen.getByText("Recommended").closest("article")!;
    expect(
      within(recommended).getByRole("heading", { name: workflow.name }),
    ).toBeTruthy();
    expect(request).not.toHaveBeenCalled();
  });
  it("keeps the preview during creation so the draft handoff cannot be lost", async () => {
    request
      .mockResolvedValueOnce(agentDetail)
      .mockImplementationOnce(() => new Promise(() => {}));
    gallery();
    fireEvent.click(
      screen.getByRole("button", { name: `Preview ${agent.name}` }),
    );
    fireEvent.click(
      await screen.findByRole("button", { name: /create workspace draft/i }),
    );
    expect(
      screen.getByRole("button", { name: /close preview/i }),
    ).toHaveProperty("disabled", true);
  });

  it("returns keyboard focus to the recipe after closing its preview", async () => {
    request.mockResolvedValueOnce(agentDetail);
    gallery();
    const trigger = screen.getByRole("button", {
      name: `Preview ${agent.name}`,
    });
    fireEvent.click(trigger);
    fireEvent.click(
      await screen.findByRole("button", { name: /close preview/i }),
    );
    expect(document.activeElement).toBe(trigger);
  });

  it("opens existing workflow editing for a draft without copied skills", async () => {
    request
      .mockResolvedValueOnce({ ...workflow, graph: { nodes: [] } })
      .mockResolvedValueOnce({ kind: "workflow", id: "wf-1", skill_ids: [] });
    gallery();
    fireEvent.click(
      screen.getByRole("button", { name: `Preview ${workflow.name}` }),
    );
    fireEvent.click(
      await screen.findByRole("button", { name: /create workspace draft/i }),
    );
    const status = await screen.findByRole("region", {
      name: "Created workspace draft",
    });
    expect(
      within(status)
        .getByRole("link", { name: /open workflow editor/i })
        .getAttribute("href"),
    ).toBe("/w/ws-1/workflows/wf-1/edit");
    expect(
      within(status).queryByRole("link", { name: /review attached skill/i }),
    ).toBeNull();
  });
  it("shows task discovery and workspace visibility at the start route", () => {
    render(<TaskStart workspaceId="ws-1" />);
    expect(
      screen
        .getByRole("link", { name: /browse task recipes/i })
        .getAttribute("href"),
    ).toBe("/w/ws-1/templates");
    expect(screen.getByText(/workspace-visible/i)).toBeTruthy();
  });

  it("filters locally by search and category and keeps advanced transfer available", () => {
    gallery();
    fireEvent.change(screen.getByLabelText("Search recipes"), {
      target: { value: "report" },
    });
    expect(screen.queryByRole("heading", { name: agent.name })).toBeNull();
    expect(screen.getByRole("heading", { name: workflow.name })).toBeTruthy();
    fireEvent.change(screen.getByLabelText("Category"), {
      target: { value: "Knowledge" },
    });
    expect(screen.getByText(/no recipes match/i)).toBeTruthy();
    expect(request).not.toHaveBeenCalled();
    fireEvent.click(screen.getByText("Advanced template import and export"));
    expect(screen.getByLabelText("Import a FlowForge template")).toBeTruthy();
  });

  it("previews setup, sample, result, copied skills and cost before the only create action", async () => {
    request.mockResolvedValueOnce(agentDetail);
    gallery();
    expect(
      screen.queryByRole("button", { name: /create workspace draft/i }),
    ).toBeNull();
    fireEvent.click(
      screen.getByRole("button", { name: `Preview ${agent.name}` }),
    );
    const preview = await screen.findByRole("region", {
      name: "Recipe preview",
    });
    expect(within(preview).getByText(agentDetail.expected_result)).toBeTruthy();
    expect(within(preview).getByText("Connect a provider.")).toBeTruthy();
    expect(within(preview).getByText(/When/)).toBeTruthy();
    expect(within(preview).getByText(/plain language/i)).toBeTruthy();
    expect(within(preview).getByText(/provider charges/i)).toBeTruthy();
    expect(within(preview).getByText(/workspace-visible/i)).toBeTruthy();
    expect(
      within(preview).getByRole("button", { name: /create workspace draft/i }),
    ).toBeTruthy();
  });

  it("creates through the existing endpoint and offers every attached skill before opening the agent", async () => {
    request.mockResolvedValueOnce(agentDetail).mockResolvedValueOnce({
      kind: "agent",
      id: "agent-1",
      skill_ids: ["skill-a", "skill-b"],
    });
    gallery();
    fireEvent.click(
      screen.getByRole("button", { name: `Preview ${agent.name}` }),
    );
    fireEvent.click(
      await screen.findByRole("button", { name: /create workspace draft/i }),
    );
    const status = await screen.findByRole("region", {
      name: "Created workspace draft",
    });
    expect(request).toHaveBeenLastCalledWith(
      "/workspaces/ws-1/templates/faq-answer/instantiate",
      { method: "POST" },
    );
    expect(
      within(status).getByText(/review and publish.*before.*test.*publish/i),
    ).toBeTruthy();
    expect(
      within(status).getByText(/edits.*new immutable skill version/i),
    ).toBeTruthy();
    expect(
      within(status)
        .getAllByRole("link", { name: /review attached skill/i })
        .map((a) => a.getAttribute("href")),
    ).toEqual([
      "/w/ws-1/agents/skills/skill-a",
      "/w/ws-1/agents/skills/skill-b",
    ]);
    expect(
      within(status)
        .getByRole("link", { name: /open agent editor/i })
        .getAttribute("href"),
    ).toBe("/w/ws-1/agents/agent-1");
    expect(push).not.toHaveBeenCalled();
  });

  it.each([
    {
      key: "switch-routing",
      name: "Route requests by category",
      category: "Workflow basics",
      nodeType: "switch" as const,
      sample: { category: "billing" },
      expected: 'Returns {"queue": "billing-team"}.',
    },
    {
      key: "remove-duplicates",
      name: "Remove duplicate contacts",
      category: "Data cleanup",
      nodeType: "list_deduplicate" as const,
      sample: {
        items: [{ email: "ada@example.com" }, { email: "ada@example.com" }],
      },
      expected: "Keeps the first contact; count is 1 and removed is 1.",
    },
  ])(
    "discovers and previews the local $key starter through the existing gallery",
    async ({ key, name, category, nodeType, sample, expected }) => {
      const recipe: TemplateEntry = {
        key,
        name,
        category,
        kind: "workflow",
        template_version: 1,
        description: "A local workflow starter",
        setup_steps: [
          "Preview the sample, validate, then publish for a durable run.",
        ],
        sample_input: sample,
        expected_result: expected,
      };
      request
        .mockResolvedValueOnce({
          ...recipe,
          graph: {
            nodes: [{ id: "step", label: name, type: nodeType, config: {} }],
          },
        })
        .mockResolvedValueOnce({
          kind: "workflow",
          id: "local-draft",
          skill_ids: [],
        });
      render(
        <TemplateGallery
          workspaceId="ws-1"
          templates={[agent, recipe]}
          canCreate
        />,
      );
      fireEvent.change(screen.getByLabelText("Category"), {
        target: { value: category },
      });
      expect(screen.queryByRole("heading", { name: agent.name })).toBeNull();
      fireEvent.click(screen.getByRole("button", { name: `Preview ${name}` }));
      const preview = await screen.findByRole("region", {
        name: "Recipe preview",
      });
      expect(request).toHaveBeenCalledWith(`/templates/${key}`);
      expect(within(preview).getByText(recipe.setup_steps![0])).toBeTruthy();
      expect(within(preview).getByText(expected)).toBeTruthy();
      expect(JSON.parse(preview.querySelector("pre")!.textContent!)).toEqual(
        sample,
      );
      expect(
        within(preview).getByText(/use local draft preview/i),
      ).toBeTruthy();
      fireEvent.click(
        within(preview).getByRole("button", {
          name: /create workspace draft/i,
        }),
      );
      const created = await screen.findByRole("region", {
        name: "Created workspace draft",
      });
      expect(request).toHaveBeenLastCalledWith(
        `/workspaces/ws-1/templates/${key}/instantiate`,
        { method: "POST" },
      );
      expect(
        within(created)
          .getByRole("link", { name: /open workflow editor/i })
          .getAttribute("href"),
      ).toBe("/w/ws-1/workflows/local-draft/edit");
    },
  );

  it.each([
    {
      nodes: [{ id: "text", label: "Text", type: "text", config: {} }],
      message: /local draft preview/i,
    },
    {
      nodes: [{ id: "llm", label: "Model", type: "llm", config: {} }],
      message: /publish.*durable full run/i,
    },
  ])(
    "explains the applicable workflow run boundary",
    async ({ nodes, message }) => {
      request.mockResolvedValueOnce({ ...workflow, graph: { nodes } });
      gallery();
      fireEvent.click(
        screen.getByRole("button", { name: `Preview ${workflow.name}` }),
      );
      const preview = await screen.findByRole("region", {
        name: "Recipe preview",
      });
      expect(within(preview).getByText(message)).toBeTruthy();
    },
  );

  it("keeps viewer preview available but disables creation and reports fetch failures", async () => {
    request
      .mockRejectedValueOnce(new Error("Preview unavailable"))
      .mockResolvedValueOnce(agentDetail);
    gallery(false);
    fireEvent.click(
      screen.getByRole("button", { name: `Preview ${agent.name}` }),
    );
    expect(await screen.findByRole("alert")).toHaveProperty(
      "textContent",
      "Preview unavailable",
    );
    fireEvent.click(
      screen.getByRole("button", { name: `Preview ${agent.name}` }),
    );
    expect(
      await screen.findByRole("button", { name: /create workspace draft/i }),
    ).toHaveProperty("disabled", true);
  });
});
