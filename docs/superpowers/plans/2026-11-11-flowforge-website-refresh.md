# FlowForge Website Refresh Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task.

**Goal:** Make FlowForge's public website accurately demonstrate the current product and guide first-time users into a clear, low-friction start.

**Architecture:** Refine the existing Next.js landing page and shared CSS tokens/components rather than introduce a second UI system. Keep product claims tied to shipped features, use the existing workflow preview as the proof point, and make each primary action resolve to a real route.

**Tech Stack:** Next.js 16, React 19, TypeScript, custom CSS tokens, Lucide, Vitest and Playwright/manual browser verification if an available GUI exists.

**Spec:** `docs/superpowers/specs/2026-11-11-noncoder-creation-experience-design.md`; local UI guidance: `.agents/skills/ui-ux-pro-max/SKILL.md` and `.agents/skills/ui-styling/SKILL.md`.

## Global Constraints

- Use the UI-UX recommendation for an AI-native SaaS product demo and feature layout, while retaining FlowForge's existing semantic colors, light surfaces, Lucide icon family and custom CSS system.
- Keep the public landing page focused on an accurate current product demo and simple start action.
- Form errors stay inline, keyboard focus stays visible, mobile layouts preserve readable canvas/list alternatives, and motion respects reduced-motion preferences.
- Keep one source of truth for existing tokens and shared product claims.

## Review Focus

1. Hero and feature statements map to current verified functionality; tests guard stale roadmap language.
2. All CTA links resolve to valid destinations for signed-in and signed-out users.
3. Workflow demo remains understandable at narrow widths and does not rely on hover-only or motion-only cues.
4. Keyboard users can reach and identify primary actions; focus indicators remain visible.
5. Reduced-motion settings disable decorative animation without removing information.

---

### Task 1: Product narrative and route contract

**Files:** `frontend/src/app/page.tsx`, landing-page model/tests if present, `frontend/src/app/globals.css` or current global stylesheet.

**Interfaces:** Keep existing Next.js route behavior and auth destinations. Public visitor primary action routes to registration; signed-in action follows current workspace/app routing if supported. Use existing palette tokens `--color-background`, `--color-foreground`, and `--color-primary` and existing Lucide icon imports.

- [x] Add rendered-page tests for CTA destination, accurate feature labels and the absence of copy that promises unshipped live capabilities.
- [x] Run focused tests and record the failing behavior; implementer observed four initial failures, then expanded coverage to six route/copy tests.
- [x] Redesign hero hierarchy around the describe-task → configure-recipe → test journey, with registration CTA and a secondary product-demo jump link.
- [x] Rewrite feature sections around actual agent, workflow, template, integration, skill and approval behavior; distinguish examples from live actions.
- [x] Verify tests and commit `f2aec8f`; independent review approved with no findings.

### Task 2: Responsive demo and accessibility polish

**Files:** `frontend/src/app/page.tsx`, landing styles in `frontend/src/app/globals.css` or the existing landing stylesheet, related component tests.

- [x] Add tests for reduced-motion behavior and accessible names/focus behavior.
- [x] Run focused tests and confirm four intended failures.
- [x] Polish the existing workflow illustration with clear step labels, verified contrast, visible focus behavior and narrow-screen stacked outcomes. Respect reduced-motion preferences.
- [x] Run frontend tests (100), typecheck, lint, API drift and production build. No browser walkthrough performed; manual review is assigned to the user as requested.
- [x] Commit `3773d05`; independent review approved with no findings.

### Task 3: Manual GUI test guide and product documentation

**Files:** `docs/PROJECT_STATUS.md`, `docs/DEVELOPMENT_PHASES.md`, `docs/manual-testing/noncoder-creation.md`.

- [x] Align product status and development phases with the actual shipped feature inventory: 15 recipes, 11 skills and 22 workflow node types.
- [x] Write a concise manual GUI route for registration/workspace start, template preview/creation, provider setup, skill publishing, local preview and published full run, including the new practical node recipes.
- [x] Confirm documented actions/routes exist; 21 local Markdown links and 16 route variants checked; independent docs review approved.
- [x] Commit `941cb4a`. Signed-in GUI and live-provider acceptance remain explicitly for the user.

