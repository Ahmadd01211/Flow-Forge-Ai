// @vitest-environment jsdom
import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import Landing from "./page";

afterEach(cleanup);

describe("public landing page", () => {
  it("starts workspace creation at registration and keeps the existing sign-in route", () => {
    render(<Landing />);
    expect(
      screen
        .getByRole("link", { name: /create your workspace/i })
        .getAttribute("href"),
    ).toBe("/register");
    expect(
      screen.getByRole("link", { name: /sign in/i }).getAttribute("href"),
    ).toBe("/login");
  });

  it("opens the existing app entry point for returning workspace members", () => {
    render(<Landing />);
    expect(
      screen.getByRole("link", { name: /open workspace/i }).getAttribute("href"),
    ).toBe("/app");
  });

  it("jumps from the secondary action to an explicitly illustrative product demo", () => {
    render(<Landing />);
    const destination = screen
      .getByRole("link", { name: /see the product demo/i })
      .getAttribute("href");
    expect(destination).toBe("#product-demo");
    const demo = document.getElementById(destination!.slice(1));
    expect(demo).toBeTruthy();
    expect(demo!.textContent).toMatch(/illustrative workflow/i);
    expect(demo!.textContent).toMatch(/does not run|no live actions/i);
    expect(within(demo!).queryByRole("button")).toBeNull();
  });

  it("explains the shipped agents, workflows, templates, integrations, skills and approvals", () => {
    render(<Landing />);
    for (const feature of [
      "Agents",
      "Workflows",
      "Templates",
      "Integrations",
      "Skills",
      "Approvals",
    ]) {
      expect(
        screen.getByRole("heading", {
          level: 3,
          name: new RegExp(feature, "i"),
        }),
      ).toBeTruthy();
    }
    expect(screen.getByText(/workspace-visible draft/i)).toBeTruthy();
    expect(screen.getByText(/verify a provider key/i)).toBeTruthy();
  });

  it("states the setup and publication boundaries for tests and full workflow runs", () => {
    const { container } = render(<Landing />);
    expect(container.textContent).toMatch(
      /local (draft )?preview.*supported local steps/i,
    );
    expect(container.textContent).toMatch(/publish.*full workflow run/i);
    expect(container.textContent).toMatch(/model calls.*provider.*cost/i);
  });

  it("does not sell roadmap execution or unconfigured external actions as live capabilities", () => {
    const { container } = render(<Landing />);
    expect(container.textContent).not.toMatch(
      /platform is being built|capabilities introduced as they are verified|live demo|connect any app|no setup required|runs automatically/i,
    );
  });
});
