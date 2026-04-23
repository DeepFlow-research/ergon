# Test refactor — plan folder

**Status:** draft for review — nothing landed yet.
**Date:** 2026-04-23.
**Scope:** complete rebuild of the testing posture, smoke program, and CI integration. Single merge-ready PR when all nine docs are reviewed and the code matches.

## Read order

1. [`00-program.md`](00-program.md) — goals, non-goals, tier model, invariants, budgets, merge checklist. The "why + what."
2. [`01-fixtures.md`](01-fixtures.md) — directory layout + code sketches for every shared base, per-env worker/leaf/criterion, registration hook. No LLM, no pydantic-ai toolkits; deterministic Python only.
3. [`02-drivers-and-asserts.md`](02-drivers-and-asserts.md) — pytest driver template + per-env Postgres assertion catalogs. Describes every SQLModel row read after a smoke run.
4. [`03-dashboard-and-playwright.md`](03-dashboard-and-playwright.md) — `/api/test/*` harness contract (what's there, what's new), `BackendHarnessClient` TS shape, Playwright spec template, per-env deltas, screenshot capture points.
5. [`04-ci-and-workflows.md`](04-ci-and-workflows.md) — `ci-fast.yml` job layout, `e2e-benchmarks.yml` PR-trigger matrix, docker-layer-cache fix, screenshot ref push + PR comment, cleanup on PR close.
6. [`05-deletions.md`](05-deletions.md) — full manifest of files / RFCs / plans / registry slugs / brainstorms to delete on the landing PR.
7. [`06-phases.md`](06-phases.md) — phased delivery plan inside the single PR (Phase A done; B–F ahead; Phase G as the concluding step that wires `BaseSandboxManager.reconnect` through `CriterionRuntime` so criteria attach via the manager and hold the task's sandbox open throughout evaluation). Each phase has scope, deliverables, acceptance gate.

## Principle

Each doc is **self-contained for its audience**. If a reviewer only reads one doc, that doc must be enough to execute its part. Cross-references are explicit links, not vague gestures. When two docs disagree, `00-program.md` wins; when `00-program.md` and reality disagree, we amend `00-program.md` and re-review.

## When this plan lands

1. Delete every file listed in [`05-deletions.md`](05-deletions.md) in the same PR as the new code.
2. Update `docs/architecture/07_testing.md` to point at `docs/superpowers/plans/test-refactor/`.
3. Delete `docs/superpowers/plans/test-refactor/` itself once the rebuild is done and `07_testing.md` fully documents the standing system.

Keeping this folder around after landing is an anti-pattern — it's planning, not documentation.
