# PR 3 — Run Workspace Composition

## Purpose

Make the run workspace feel like one debugger surface instead of stitched panes:
header, graph, drawer, and timeline should coordinate around selection and time.

## Reference Images

```text
docs/rfcs/active/2026-05-20-frontend-quality-and-design-system-refresh/assets/current-run-workspace.png
docs/rfcs/active/2026-05-20-frontend-quality-and-design-system-refresh/assets/archive-run-workspace.png
```

## Scope

- Strengthen run header and metric strip.
- Fix token/cost/score/task readouts.
- Polish graph canvas spacing, controls, legend, minimap, and selected state.
- Make drawer feel attached to selected node/time.
- Make timeline supportive and readable.

## Likely Files

```text
ergon-dashboard/src/app/run/[runId]/page.tsx
ergon_core/ergon_core/core/views/runs/models.py
ergon_core/ergon_core/core/views/runs/service.py
ergon-dashboard/src/components/run/RunWorkspacePage.tsx
ergon-dashboard/src/components/run/RunStatusBar.tsx
ergon-dashboard/src/components/run/useRunDisplayState.ts
ergon-dashboard/src/components/run/useRunPanelLayout.ts
ergon-dashboard/src/components/dag/DAGCanvas.tsx
ergon-dashboard/src/components/dag/LevelSelector.tsx
ergon-dashboard/src/components/dag/TaskNode.tsx
ergon-dashboard/src/components/workspace/TaskWorkspace.tsx
ergon-dashboard/src/features/activity/*
ergon-dashboard/src/lib/run-state/metrics.ts
ergon-dashboard/tests/e2e/run.snapshot.spec.ts
ergon-dashboard/tests/e2e/run.delta.spec.ts
```

## Implementation Steps

1. Extend `RunSnapshotDto` with a run header metrics object or explicit fields:
   `total_tasks`, `completed_tasks`, `failed_tasks`, `running_tasks`,
   `total_tokens`, `token_breakdown`, `total_cost_usd`, `cost_observed`,
   `final_score`, and duration.
2. Populate the run metrics in `RunReadService.build_run_snapshot` from the
   same source helpers used by PR 2:
   - task counts from snapshot task state;
   - score from evaluation summary;
   - tokens from persisted provider usage and context-event `token_ids`, broken
     down by prompt, assistant text, thinking, tool call, tool result, cached,
     and unknown;
   - cost from fixed core cost aggregation with `cost_observed = true`, not the
     current default `summary_json.total_cost_usd = 0.0`;
   - unavailable values as explicit `None`, not omitted.
3. Regenerate/update frontend REST contracts and parse the new fields in the
   dashboard contract layer.
4. Add a shared frontend formatter module for task count, tokens, cost, score,
   duration, and unavailable metric state.
5. Tighten run header hierarchy: title, status, live/snapshot, metrics, actions.
6. Tune graph controls and layout spacing to reduce toolbar/minimap overlap.
7. Improve selected node and selected timeline event treatment.
8. Make drawer header and tabs visually attached to selected context.
9. Remove or reuse `RunStatusBar`; do not leave dead primitives.

## UX Verification

Product tasks:

- Is this view live or a snapshot?
- Which task is selected?
- What failed or blocked downstream work?
- What are the task count, score, cost, and tokens, or why are they unavailable?
- What timeline event corresponds to the selected graph state?

Screenshots:

- run workspace no drawer;
- drawer open;
- selected timeline activity;
- failed smoke run;
- completed smoke run.

## Tests

```sh
pnpm -C ergon-dashboard run test:unit
pnpm -C ergon-dashboard exec playwright test tests/e2e/run.snapshot.spec.ts
pnpm -C ergon-dashboard exec playwright test tests/e2e/run.delta.spec.ts
```

Add tests for:

- run header token breakdown mapping;
- observed versus unavailable cost display;
- backend run snapshot metric projection;
- frontend contract parsing;
- formatting helpers.

## Acceptance

- Header metrics are real or deliberately unavailable.
- The run workspace uses the same metric names and formatters as the experiment
  detail page.
- Graph, drawer, and timeline align visually and behaviorally.
- No toolbar, minimap, graph, drawer, or timeline overlap at `2048x1228`.
- Node labels, status chips, metrics, and controls remain legible.
- Failed, blocked, completed, pending, and running work remain distinguishable.
