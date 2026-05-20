# PR 2 — Experiment Page And RunMetricExplorer

## Purpose

Make experiment detail a control surface: answer what happened, which runs are
interesting, and what to inspect next.

## Scope

- Refresh `/experiments/[definitionId]` layout and metric hierarchy.
- Build the reusable `RunMetricExplorer` for run-level metrics.
- Improve run table styling and filtering.
- Extend the backend and frontend contracts so run-level metrics are first-class
  data for the experiment page.

## Likely Files

```text
ergon-dashboard/src/app/experiments/[definitionId]/page.tsx
ergon-dashboard/src/app/experiments/page.tsx
ergon_core/ergon_core/core/views/experiments/models.py
ergon_core/ergon_core/core/views/experiments/service.py
ergon_core/ergon_core/core/views/runs/models.py
ergon_core/ergon_core/core/views/runs/service.py
ergon_core/ergon_core/core/infrastructure/http/routes/experiments.py
ergon-dashboard/src/lib/server-data/experiments.ts
ergon-dashboard/src/lib/server-data/runs.ts
ergon-dashboard/src/lib/contracts/rest.ts
ergon-dashboard/src/generated/rest/contracts.ts
ergon-dashboard/src/lib/run-state/metrics.ts
ergon-dashboard/src/lib/formatDuration.ts
ergon-dashboard/src/components/common/StatusBadge.tsx
ergon-dashboard/src/components/experiments/RunMetricExplorer.tsx
ergon-dashboard/src/components/experiments/RunMetricExplorer.test.tsx
tests/contracts or ergon_core view tests
ergon-dashboard/tests/contracts/server-data.contract.test.ts
ergon-dashboard/tests/e2e/*.smoke.spec.ts
```

Create `components/experiments/` if it does not exist.

## Data Contract Plan

Do not make the frontend scrape or infer metrics from display text. Add a
purpose-built run analytics projection to the experiment detail contract.

Backend DTO work:

- Add a nested `ExperimentRunMetricsDto` to `ExperimentRunRowDto`. Keep any
  existing row-level score/duration fields as compatibility shims until the
  dashboard only reads `metrics`.
- Include these run-level fields with explicit `None` for unknown values:
  - `run_id`
  - `run_name` or display label
  - `status`
  - `sample_label` / `instance_key`
  - `score` or `return_value`
  - `duration_ms`
  - `total_tasks`
  - `tool_call_count`
  - `total_cost_usd`
  - `total_tokens`
  - `token_breakdown`
  - `model_target`
  - `evaluator_slug`
  - `error_summary`
- Populate available values in `ExperimentReadService._run_row` from
  `RunRecord`, `RunGraphNode`, run summary JSON, evaluations, and context/event
  rows.
- Metric source facts from the current schema:
  - `tool_call_count` is available from `run_context_events`: count rows where
    `run_id` matches and `event_type = "tool_call"`.
  - `total_tokens` is partially available from `run_context_events.payload`.
    Each persisted `ContextPartChunkLog` already has a `token_ids` field, but
    current smoke data records null token IDs. Before the chart reads token
    metrics, update the LLM/provider adapter path to persist provider token
    usage alongside token IDs:
    - prompt/input tokens;
    - completion/output tokens;
    - reasoning tokens when the provider reports them;
    - tool-call argument tokens when the provider separates them;
    - cached/read tokens when the provider reports cache accounting;
    - local `token_ids` for generated parts when available.
  - Store token metrics at the context-event/generation-turn boundary, not by
    tokenizing rendered text later. The read model should aggregate them into
    `total_tokens` plus `token_breakdown` grouped by semantic type:
    `prompt`, `assistant_text`, `thinking`, `tool_call`, `tool_result`,
    `cached`, and `unknown`.
  - `total_cost_usd` exists today only in `runs.summary_json`, but the current
    finalize path writes `RunCompletionData.total_cost_usd`, whose default is
    `0.0` and has no observed provider/tool-cost source. Fix core cost
    calculation before showing cost in the frontend:
    - persist provider pricing inputs or resolved per-request cost with the
      same generation-turn/token-usage record;
    - include sandbox/tool costs only from explicit cost events;
    - aggregate observed costs into run completion summary;
    - mark cost as observed so the read model can distinguish real zero from
      missing instrumentation.
- Add tests for the DTO projection so a smoke experiment produces stable metric
  rows.

Frontend contract work:

- Regenerate or update REST contracts after backend DTO changes.
- Parse the fields in `ergon-dashboard/src/lib/contracts/rest.ts`.
- Map them in `ergon-dashboard/src/lib/server-data/experiments.ts` into a
  normalized `RunMetricPoint` array.
- Keep `RunMetricExplorer` purely presentational: it receives metric descriptors
  and points, and does not know about backend DTO quirks.

Frontend destination:

- Experiment summary cards consume aggregate analytics from
  `ExperimentDetail.analytics`.
- `RunMetricExplorer` consumes normalized run metric points.
- The run table consumes the same normalized rows so hover, chart, and table
  values cannot disagree.

## RunMetricExplorer Spec

Input:

- metric descriptors: key, label, unit, formatter, availability;
- run points: run id, status, sample, metric values, hover metadata;
- mode: `1D` or `2D`;
- selection: one metric for `1D`, two metrics for `2D`.

Behavior:

- `1D < 5` numeric values: ranked list or run strip.
- `1D 5-19`: rug/dot strip or simple histogram.
- `1D 20+`: histogram with p50/p95 markers.
- `2D 3+`: scatter plot.
- `2D < 10`: show "too few points for trend".
- `2D 20+`: do not ship trendline/correlation in the first PR. Add a follow-up
  only after each metric pair has an explicit semantic interpretation.
- hover shows all run metadata, not only plotted axes.
- click navigates to the run workspace.

First metric set and source:

- score or return: `ExperimentRunMetricsDto.score` / `return_value`;
- duration: `duration_ms`;
- task count: `total_tasks`;
- tool-call count: count of persisted `run_context_events` with
  `event_type = "tool_call"`;
- tokens: persisted provider token usage plus local token IDs, aggregated into
  total and semantic breakdown fields;
- cost: observed core cost calculation from persisted provider/tool/sandbox cost
  inputs, never the current default `0.0`.

## UX Verification

Product tasks:

- What is this experiment?
- How many runs passed, failed, or are active?
- Which run should I inspect first?
- Is poor score related to runtime, task count, or another selected metric?
- Can I hover a point and decide whether to open the run?

Screenshots:

- small smoke experiment with 2-3 runs;
- metric explorer in `1D` mode using fixture or seeded data with at least 5
  numeric values;
- metric explorer in `2D` mode using fixture or seeded data with at least 3
  numeric points;
- hover tooltip state;
- filtered failed-runs table state.

## Tests

```sh
pnpm -C ergon-dashboard run test:unit
pnpm -C ergon-dashboard exec playwright test tests/e2e/swebench-verified.smoke.spec.ts
```

Add unit tests for:

- provider token usage persistence and token breakdown aggregation;
- core cost calculation and observed-cost marker behavior;
- backend metric projection;
- frontend metric normalization;
- formatter behavior;
- threshold selection for `1D`/`2D` mode;
- empty/unavailable metric handling.

## Acceptance

- The experiment page explains status, score, runtime, errors, and run count at
  a glance.
- `RunMetricExplorer` degrades gracefully for small experiments.
- No misleading distribution or trend claims are shown.
- Hover gives enough run context to choose whether to open the run.
- Run table is denser, more scannable, and consistent with Ergon tokens.
- Backend, REST contract, server-data loader, chart, and table all use the same
  run metric model.
