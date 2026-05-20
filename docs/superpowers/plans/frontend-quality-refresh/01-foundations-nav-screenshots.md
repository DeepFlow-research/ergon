# PR 1 — Foundations, Navigation, And Screenshot Baseline

## Purpose

Make the dashboard safe to redesign by fixing global visual foundations, hiding
dead navigation, and establishing repeatable screenshot evidence.

## Scope

- Fix font fallback so the dashboard cannot collapse into browser serif type.
- Normalize shared primitives and token usage where needed for later PRs.
- Remove or hide dead `Models` and `Settings` top-nav links.
- Make `Runs` navigation intentional by adding a temporary, deliberate
  unavailable page in PR 1. PR 5 replaces this with the endpoint-backed runs
  index.
- Document screenshot capture commands for the stack.

## Likely Files

```text
ergon-dashboard/src/app/globals.css
ergon-dashboard/src/app/layout.tsx
ergon-dashboard/src/components/common/ClientLayout.tsx
ergon-dashboard/src/components/shell/Topbar.tsx
ergon-dashboard/src/app/runs/page.tsx
ergon-dashboard/src/app/models/page.tsx
ergon-dashboard/src/app/settings/page.tsx
ergon-dashboard/tests/e2e/health.spec.ts
ergon-dashboard/tests/e2e/*.spec.ts
```

Delete or stop exposing `models`/`settings` routes only if nothing else links to
them. Prefer hiding from nav first if deletion would create unrelated churn.

## Implementation Steps

1. Inspect `Topbar.tsx` and app routes to see how active nav state is computed.
2. Fix CSS font variables:
   - `--font: var(--font-inter, Inter), ...`
   - `--mono: var(--font-jetbrains-mono, "JetBrains Mono"), ...`
3. Hide or remove `Models` and `Settings` from visible nav.
4. Update `Runs` behavior:
   - keep the `Runs` nav item visible because it is a real product surface;
   - replace the current inert/broken behavior with a deliberate unavailable
     state that says the run index lands in PR 5;
   - include a clear route back to experiments and a note that individual run
     workspaces remain available from experiment detail rows.
5. Add or update e2e/unit assertions for visible nav items.
6. Capture baseline screenshots for experiment detail, run workspace, and rubric
   drawer states.

## UX Verification

Product tasks:

- A user can see only nav items that do something deliberate.
- A user can click `Runs` and understand the result.
- The page remains sans-serif if web fonts are delayed.

Screenshots:

- top nav at `2048x1228`;
- experiment detail before/after;
- run workspace before/after.

## Tests

```sh
pnpm -C ergon-dashboard run test:unit
pnpm -C ergon-dashboard exec playwright test tests/e2e/health.spec.ts
```

Add targeted Playwright checks if no current test covers nav behavior.

## Acceptance

- No dead top-nav links are visible.
- `Runs` nav has an obvious outcome.
- Font fallback is robust.
- Screenshot commands are documented for later PRs.
- No broad redesign lands in this PR.
