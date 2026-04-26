# MAS Run Visual Debugger — plan folder

**Status:** draft for review — branch planning only; no frontend implementation landed yet.
**Date:** 2026-04-26.
**Branch:** `feature/mas-run-visual-debugger-plan`.
**Design reference:** `ergon-dashboard/mockups/mas-activity-stack-debugger.html`.

## Read order

1. [`00-program.md`](00-program.md) — product goal, non-goals, UX invariants, DTO stance, merge checklist.
2. [`05-implementation-shape.md`](05-implementation-shape.md) — reviewer-facing "how": domains, file ownership, add/refactor/delete plan, test layout.
3. [`01-contracts-and-state.md`](01-contracts-and-state.md) — event/DTO inventory, activity-stack domain model, replay rules, and where backend contract changes are actually needed.
4. [`02-frontend-implementation.md`](02-frontend-implementation.md) — component and layout plan for the three-pane visual debugger.
5. [`03-tests-and-e2e.md`](03-tests-and-e2e.md) — unit/component/e2e coverage, screenshot contract, and harness DTO additions.
6. [`06-fast-feedback-and-visual-review.md`](06-fast-feedback-and-visual-review.md) — TDD fixture loop, coarse layout geometry checks, and local-only PNG review workflow.
7. [`04-phases.md`](04-phases.md) — phased delivery order with acceptance gates.

## Principle

The dashboard should be a visual debugger for a MAS run, not an agent swimlane view. The durable axes are graph state, task-scoped events, and wall-clock overlap. Agents/workers are labels on events, not layout anchors.

When documents disagree, `00-program.md` wins. When `00-program.md` and code reality disagree, update `00-program.md` first and re-review before implementing.
