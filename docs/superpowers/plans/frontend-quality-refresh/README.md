# Frontend Quality Refresh — PR Stack Plan

**Status:** draft implementation plan.
**Date:** 2026-05-20.
**RFC:** [`docs/rfcs/active/2026-05-20-frontend-quality-and-design-system-refresh/README.md`](../../../rfcs/active/2026-05-20-frontend-quality-and-design-system-refresh/README.md).

## Goal

Ship the dashboard frontend quality refresh as a stack of reviewable PRs. Each
PR should improve one coherent surface and include UX evidence: before/after
screenshots, product task checks, and automated guardrails.

## Read Order

1. [`01-foundations-nav-screenshots.md`](01-foundations-nav-screenshots.md)
2. [`02-experiment-page-run-metric-explorer.md`](02-experiment-page-run-metric-explorer.md)
3. [`03-run-workspace-composition.md`](03-run-workspace-composition.md)
4. [`04-rubric-drawer-evaluation.md`](04-rubric-drawer-evaluation.md)
5. [`05-index-pages.md`](05-index-pages.md)
6. [`06-archive-quality-rules.md`](06-archive-quality-rules.md)

## Shared UX Gate

Every PR in this stack must satisfy the RFC's `UX Verification` section:

- fixed viewport before/after screenshots;
- product task checks;
- visual checklist;
- automated guardrails;
- explicit contract fields, endpoint changes, and display handling for any
  unavailable data.

Do not treat "looks better" as done. A PR is done when the target user task is
easier to complete and the screenshot evidence makes the improvement concrete.

## Suggested Branch Stack

```text
codex/frontend-quality-01-foundations
codex/frontend-quality-02-experiment-page
codex/frontend-quality-03-run-workspace
codex/frontend-quality-04-rubric-drawer
codex/frontend-quality-05-index-pages
codex/frontend-quality-06-quality-rules
```

## Baseline Commands

Run from repo root:

```sh
pnpm -C ergon-dashboard run test:unit
pnpm -C ergon-dashboard exec playwright screenshot --full-page --viewport-size=2048,1228 \
  http://localhost:3001/experiments/52287ee2-8868-4959-951e-053f1a94c992 \
  /tmp/ergon-current-experiment.png
pnpm -C ergon-dashboard exec playwright screenshot --full-page --viewport-size=2048,1228 \
  http://localhost:3001/run/2709c08b-de67-402c-b081-18ee5994ee33 \
  /tmp/ergon-current-run.png
```

Use `ergon start` first when local dashboard/API/Postgres are not already up.
