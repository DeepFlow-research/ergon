# PR 5 — Experiment And Run Index Pages

## Purpose

Make navigation mature: users should find experiments and runs without starting
from a remembered URL or clicking through an experiment detail page.

## Reference Images

```text
docs/rfcs/active/2026-05-20-frontend-quality-and-design-system-refresh/assets/archive-experiment-page.png
docs/rfcs/active/2026-05-20-frontend-quality-and-design-system-refresh/assets/current-experiment-page.png
```

## Scope

- Upgrade `/experiments` into a dense operational index.
- Build `/runs` as a real endpoint-backed index.
- Reuse table, filter, badge, metric, empty/error primitives.
- Ensure `Runs` nav no longer feels inert.

## Likely Files

```text
ergon-dashboard/src/app/experiments/page.tsx
ergon-dashboard/src/app/runs/page.tsx
ergon_core/ergon_core/core/views/experiments/models.py
ergon_core/ergon_core/core/views/experiments/service.py
ergon_core/ergon_core/core/views/runs/models.py
ergon_core/ergon_core/core/views/runs/service.py
ergon_core/ergon_core/core/infrastructure/http/routes/runs.py
ergon-dashboard/src/lib/server-data/experiments.ts
ergon-dashboard/src/lib/server-data/runs.ts
ergon-dashboard/src/components/common/SearchInput.tsx
ergon-dashboard/src/components/common/StatusBadge.tsx
ergon-dashboard/src/components/experiments/*
ergon-dashboard/tests/contracts/server-data.contract.test.ts
ergon-dashboard/tests/e2e/health.spec.ts
```

## Implementation Steps

1. Extend the `/runs` API route to expose `RunReadService.list_runs` as a real
   dashboard endpoint with pagination/filter parameters:
   - `limit`;
   - `status`;
   - `definition_id`;
   - `experiment`;
   - `offset` for first-pass pagination.
2. Extend `RunSummaryDto` so the run index can render without fetching every
   run snapshot:
   - run id/name;
   - experiment/definition identity;
   - benchmark and instance/sample label;
   - status;
   - started/completed/latest activity timestamps;
   - duration;
   - score/return;
   - task counts;
   - model/evaluator;
   - error summary.
3. Extend experiment list summaries with the columns needed by the index:
   run counts, status counts or failure count, latest activity, average score,
   average duration, model/evaluator defaults.
4. Regenerate/update frontend contracts and server-data loaders for
   `/experiments` and `/runs`.
5. Build shared dense table patterns:
   - compact row height;
   - mono numeric cells;
   - status badges;
   - muted secondary text;
   - consistent empty/error/loading states.
6. Add filters/search for status, benchmark, score, run count, and activity
   against the exposed fields.
7. Link experiment rows to detail and run rows to run workspace.

## UX Verification

Product tasks:

- What is currently running?
- What failed recently?
- Which experiment should I open next?
- Can I find a run without opening its experiment first?
- Does `Runs` nav have an obvious outcome?

Screenshots:

- experiment index populated;
- experiment index empty/error using fixture or mocked loader response;
- runs index populated;
- runs index empty/error using fixture or mocked loader response;
- search/filter state.

## Tests

```sh
pnpm -C ergon-dashboard run test:unit
pnpm -C ergon-dashboard exec playwright test tests/e2e/health.spec.ts
```

Add backend route/service tests and frontend server-data contract tests for the
new list shapes.

## Acceptance

- Experiment index answers running/failed/recent/open-next questions.
- Runs index renders from the list endpoint without opening each run snapshot.
- Row height, alignment, badge style, numeric formatting, and filters are
  consistent across experiment and run indexes.
- No visible dead nav remains.
