# PR 4 — Rubric Drawer And Evaluation Visibility

## Purpose

Make evaluation explainable. A low score should be traceable to criteria,
aggregation, reasoning, skipped states, and errors without raw JSON spelunking.

## Reference Images

```text
docs/rfcs/active/2026-05-20-frontend-quality-and-design-system-refresh/assets/current-rubric-drawer.png
docs/rfcs/active/2026-05-20-frontend-quality-and-design-system-refresh/assets/archive-rubric-drawer.png
```

## Scope

- Replace noisy graph `R` marker with a quieter evaluation indicator.
- Preserve evaluation lens mode.
- Upgrade `EvaluationPanel` hierarchy and styling.
- Show pass/fail/skipped/error states explicitly.
- Avoid adding fake actions unless backend behavior exists.

## Likely Files

```text
ergon-dashboard/src/components/panels/EvaluationPanel.tsx
ergon_core/ergon_core/core/views/runs/models.py
ergon_core/ergon_core/core/views/runs/evaluation_mapping.py
ergon_core/ergon_core/core/views/runs/snapshot.py
ergon-dashboard/src/components/dag/TaskGraphStatusIcon.tsx
ergon-dashboard/src/components/dag/TaskNode.tsx
ergon-dashboard/src/features/evaluation/contracts.ts
ergon-dashboard/src/features/evaluation/selectors.ts
ergon-dashboard/src/features/evaluation/selectors.test.ts
ergon-dashboard/src/components/workspace/TaskWorkspace.tsx
ergon-dashboard/tests/e2e/*.smoke.spec.ts
```

## Implementation Steps

1. Make the run evaluation DTO the source of truth for drawer display. Confirm
   `RunTaskEvaluationDto` exposes evaluator, aggregation, total/max/normalized
   score, stages, failed gate, and criterion results.
2. Extend the backend DTO/mapping if any drawer field is missing:
   criterion status, weight, contribution, input, feedback, model reasoning,
   skipped reason, observation metadata, and error payload should be explicit
   fields.
3. Define a normalized frontend evaluation view model in
   `features/evaluation/selectors.ts` so `EvaluationPanel` does not interpret
   raw DTOs directly.
4. Replace graph marker with a tokenized indicator that survives zoom without
   visual noise.
5. Rework `EvaluationPanel`:
   - task/evaluation context;
   - rubric summary;
   - score/contribution composition;
   - compact criterion rows;
   - expanded criterion detail;
   - explicit skipped/error display.
6. Add disabled or hidden action affordances based on explicit backend support
   flags, not hardcoded guesses.

## UX Verification

Product tasks:

- What score did this task receive?
- How was the score aggregated?
- Which criterion drove the result?
- What did the evaluator reason?
- Was a criterion skipped or errored?

Screenshots:

- passing evaluation;
- failing/partial evaluation using fixture or seeded data;
- skipped or errored state using fixture or seeded data;
- graph with evaluation indicator visible at normal zoom.

## Tests

```sh
pnpm -C ergon-dashboard run test:unit
pnpm -C ergon-dashboard exec playwright test tests/e2e/swebench-verified.smoke.spec.ts
```

Add or update unit tests for backend mapping, evaluation selectors, labels, and
skipped/error rendering.

## Acceptance

- A low score is explainable from the UI.
- Pass/fail/skipped/error are visually distinct but not noisy.
- The drawer hierarchy matches the archive direction: summary, composition,
  criteria, expanded detail, actions.
- Evaluation markers do not clutter the graph.
- No rubric action appears enabled unless it works.
