// @vitest-environment jsdom
import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import Landing from "./page";

afterEach(() => {
  cleanup();
  document.head.querySelectorAll("style").forEach((style) => style.remove());
});

// jsdom does not evaluate media queries. Replay the real stylesheet's matching
// rules to check the CSS contract without pretending to measure browser layout.
function applyStyles(width = 1280, reducedMotion = false) {
  const source = document.createElement("style");
  source.textContent = readFileSync("src/app/globals.css", "utf8");
  document.head.append(source);
  const rules = Array.from(source.sheet!.cssRules).flatMap((rule) => {
    if (!(rule instanceof CSSMediaRule)) return [rule.cssText];
    const query = rule.conditionText;
    const maximum = query.match(/max-width:\s*(\d+)px/);
    const minimum = query.match(/min-width:\s*(\d+)px/);
    const matches = query.includes("prefers-reduced-motion")
      ? reducedMotion
      : (maximum || minimum) &&
        (!maximum || width <= Number(maximum[1])) &&
        (!minimum || width >= Number(minimum[1]));
    return matches ? Array.from(rule.cssRules, (child) => child.cssText) : [];
  });
  source.remove();
  const active = document.createElement("style");
  active.textContent = rules.join("\n");
  document.head.append(active);
}

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
      screen
        .getByRole("link", { name: /open workspace/i })
        .getAttribute("href"),
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

  it("gives navigation and every action an unambiguous accessible name", () => {
    render(<Landing />);
    applyStyles();
    const navigation = screen.getByRole("navigation", {
      name: "Main navigation",
    });
    expect(
      within(navigation)
        .getByRole("link", { name: "FlowForge home" })
        .getAttribute("href"),
    ).toBe("/");
    for (const name of [
      "How it works",
      "Built for control",
      "API reference",
      "Sign in",
      "Start building",
      "Create your workspace",
      "See the product demo",
      "Build your first draft",
      "Get started with FlowForge",
      "Open workspace",
    ]) {
      const link = screen.getByRole("link", { name });
      link.focus();
      expect(document.activeElement).toBe(link);
      expect(getComputedStyle(link).outline).toContain("3px");
    }
  });

  it("provides a named, described and focusable destination for the demo jump", () => {
    render(<Landing />);
    const demo = screen.getByRole("region", { name: "Support ticket triage" });
    expect(demo.id).toBe("product-demo");
    const caption = document.getElementById(
      demo.getAttribute("aria-describedby")!,
    );
    expect(caption?.textContent).toMatch(
      /does not run a model or take live actions/i,
    );
    demo.focus();
    expect(document.activeElement).toBe(demo);
    expect(demo.tabIndex).toBe(-1);
    applyStyles();
    expect(getComputedStyle(demo).outline).toContain("3px");
    expect(within(demo).queryByRole("button")).toBeNull();
  });

  it("keeps the workflow's ordered steps and both route outcomes readable on narrow screens", () => {
    render(<Landing />);
    const steps = screen.getByRole("list", { name: "Support triage steps" });
    const items = within(steps).getAllByRole("listitem");
    expect(items).toHaveLength(3);
    expect(items[0].textContent).toMatch(
      /step 1.*sample input.*support ticket/i,
    );
    expect(items[1].textContent).toMatch(
      /step 2.*configured agent.*understand.*classify/i,
    );
    expect(items[2].textContent).toMatch(
      /step 3.*route by priority.*urgent.*escalation summary.*standard.*suggested response/i,
    );
    applyStyles(375);
    expect(getComputedStyle(steps).height).toBe("auto");
    expect(getComputedStyle(steps).gridTemplateColumns).toMatch(
      /^minmax\(0(?:px)?, 1fr\)$/,
    );
    expect(
      getComputedStyle(steps.querySelector(".preview-outcomes")!)
        .gridTemplateColumns,
    ).toMatch(/^minmax\(0(?:px)?, 1fr\)$/);
    for (const node of steps.querySelectorAll(".preview-node")) {
      expect(getComputedStyle(node).position).toBe("relative");
      expect(
        parseFloat(getComputedStyle(node.querySelector("strong")!).fontSize),
      ).toBeGreaterThanOrEqual(14);
    }
    for (const label of steps.querySelectorAll("p, small, .mini-label")) {
      expect(
        parseFloat(getComputedStyle(label).fontSize),
      ).toBeGreaterThanOrEqual(12);
    }
  });

  it("removes decorative movement in reduced-motion mode while retaining all workflow information", () => {
    render(<Landing />);
    applyStyles(1280, true);
    const demo = document.getElementById("product-demo")!;
    expect(getComputedStyle(demo).transform).toBe("none");
    for (const element of [
      demo,
      ...demo.querySelectorAll("*"),
      ...screen.getAllByRole("link"),
    ]) {
      expect(getComputedStyle(element).animation).toBe("none");
      expect(getComputedStyle(element).transition).toBe("none");
    }
    expect(demo.textContent).toMatch(
      /support ticket[\s\S]*understand[\s\S]*classify[\s\S]*escalation summary[\s\S]*suggested response/i,
    );
    expect(getComputedStyle(demo).display).not.toBe("none");
    expect(getComputedStyle(demo).visibility).not.toBe("hidden");
  });
});
