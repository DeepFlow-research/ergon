---
status: active
opened: 2026-05-20
author: charlie + agent
architecture_refs:
  - docs/architecture/05_dashboard.md
supersedes: []
superseded_by: null
---

# RFC: Frontend Quality And Design System Refresh

## Problem

The current dashboard has the right product bones, but the frontend quality is
behind the underlying system. It feels visually poorer than the older static
design exploration in `../ergon_fe_design_system`, even after replacing
cohort-era concepts with experiments.

The gap is not just missing features. The current UI has concrete visual and
interaction regressions:

- Typography can collapse to a serif browser fallback if the Next font CSS
  variable is unavailable, because `--font: var(--font-inter), ...` does not
  provide a fallback inside `var()`.
- Experiment pages are sparse and generic: large whitespace bands, repeated
  white cards, weak scan paths, and little operational hierarchy.
- Run workspace machinery is present, but composition is uneven: graph,
  inspector, and timeline can feel like stitched panes instead of one coherent
  instrument.
- Evaluation/rubric UI is functionally present but visually crude. The current
  graph `R` marker and generic evaluation cards are weaker than the old
  eval-visibility explorations.
- Some components still use generic `gray-*`, `slate-*`, and `dark:*` Tailwind
  classes instead of Ergon tokens, creating an assembled-from-parts feel.
- The old design archive still uses stale cohort language, which makes it
  dangerous to port wholesale.

The desired direction is a dense, quiet, operational dashboard: neutral chrome,
clear hierarchy, color only for state/selection/evaluation, and pages designed
for repeated inspection rather than marketing-like presentation.

## Proposal

Treat the old `ergon_fe_design_system` folder as an archive of useful visual
ideas, not a source of product vocabulary. Build a refreshed frontend quality
system in the live dashboard around current concepts:

```text
Experiments -> Runs -> Recursive task graphs -> Task workspace -> Evidence/evals
```

The refresh should happen in small vertical slices with screenshot-backed
verification. Each slice should improve a real product surface, not create a
parallel mockup world.

## Reference Images

The supporting screenshots live in
`docs/rfcs/active/2026-05-20-frontend-quality-and-design-system-refresh/assets/`.
Codex cannot directly extract the binary images attached to this chat, so these
are local equivalents captured from the live dashboard and the old local design
archive.

Experiment page:

![Current experiment page](/Users/charliemasters/Desktop/synced_vm_002/ergon/docs/rfcs/active/2026-05-20-frontend-quality-and-design-system-refresh/assets/current-experiment-page.png)

![Archive experiment page](/Users/charliemasters/Desktop/synced_vm_002/ergon/docs/rfcs/active/2026-05-20-frontend-quality-and-design-system-refresh/assets/archive-experiment-page.png)

Run workspace:

![Current run workspace](/Users/charliemasters/Desktop/synced_vm_002/ergon/docs/rfcs/active/2026-05-20-frontend-quality-and-design-system-refresh/assets/current-run-workspace.png)

![Archive run workspace](/Users/charliemasters/Desktop/synced_vm_002/ergon/docs/rfcs/active/2026-05-20-frontend-quality-and-design-system-refresh/assets/archive-run-workspace.png)

Rubric drawer:

![Current rubric drawer](/Users/charliemasters/Desktop/synced_vm_002/ergon/docs/rfcs/active/2026-05-20-frontend-quality-and-design-system-refresh/assets/current-rubric-drawer.png)

![Archive rubric drawer](/Users/charliemasters/Desktop/synced_vm_002/ergon/docs/rfcs/active/2026-05-20-frontend-quality-and-design-system-refresh/assets/archive-rubric-drawer.png)

## Comparison Tracks

The design gap is easiest to reason about as four concrete comparisons: the
current experiment page versus the archive experiment page, the current run
workspace versus the archive run workspace, the current rubric drawer versus
the archive rubric drawer, and cross-cutting polish.

### 1. Experiment Page

Current state:

- The page has the correct experiment vocabulary and live data, but it feels
  under-composed: sparse header, repeated white cards, weak visual rhythm, and
  little sense of operational priority.
- Summary metrics exist, but they do not yet form a strong readout. Score,
  runs, runtime, and cost are visually similar even though they answer
  different questions.
- The run distribution section is a list, not a diagnostic view. It does not
  yet expose pass/fail balance, runtime shape, or failed-run clustering.
- The run table is useful but plain: weak status treatment, little hierarchy
  between primary and secondary values, and no quick visual coverage of rubric
  or task health.

Target state:

- Keep the current experiment language and data model.
- Recover the archive page's stronger header, five-metric summary row,
  score/runtime distribution, run filters, compact table density, status pills,
  and row-level health cues.
- Avoid reviving archive-only cohort labels, training CTAs, or mock-only
  comparison actions until they have real product behavior.

### 2. Run Workspace

Current state:

- The run page contains the right machinery: graph, task workspace, live
  status, event tracks, minimap, and evaluation tab.
- The composition feels assembled: the graph is often small or oddly centered,
  the workspace panel is visually detached, the timeline can dominate the page,
  and the header does not clearly anchor the debugging session.
- The selected node state, live/snapshot state, and timeline state are present
  but not yet one coherent interaction model.

Target state:

- Make the graph the primary instrument and the task workspace the attached
  inspection surface.
- Recover the archive's disciplined graph framing, slim controls, clearer
  recursive task grouping, stronger run header, and timeline-as-supporting-trace
  behavior.
- Preserve the current live data and current experiment/run vocabulary.

### 3. Rubric Drawer

Current state:

- Evaluation data is available, but the UI reads as a generic tab panel rather
  than a rubric explanation surface.
- The current evaluation tab does not yet make score composition, aggregation,
  contribution, skipped criteria, errored criteria, and model reasoning easy to
  scan.
- The graph `R` marker is discoverable but visually noisy at normal zoom.

Target state:

- Port the archive rubric drawer's hierarchy: rubric header, aggregation rule,
  score summary, contribution bar, criterion rows, expanded reasoning, inputs,
  metadata, and explicit skipped/errored states.
- Keep the drawer scoped to the selected task and sequence/time context.
- Replace the heavy graph marker with a quieter tokenized evaluation indicator.

### 4. Polish

Current state:

- The app may fall back to browser serif typography when Next font variables
  are unavailable.
- Core surfaces mix Ergon tokens with generic Tailwind gray/dark-mode classes.
- Spacing, borders, shadows, pills, table cells, cards, and headers vary enough
  that screens feel generated in separate passes.

Target state:

- Repair font fallbacks, standardize primitives, and make tokens the default
  path for dashboard surfaces.
- Screenshot the key pages before and after so polish remains grounded in
  product surfaces, not abstract style cleanup.
- Keep polish quiet: fewer ornamental cards, tighter page rhythm, clear
  hierarchy, and color reserved for status, selection, and evaluation.

## Design Principles

1. **Operational density over spacious ornament.**
   Tables, metrics, graph controls, and inspector panels should be compact
   enough for scanning and repeated use.

2. **One visual language.**
   Core dashboard surfaces should use Ergon tokens from
   `ergon-dashboard/src/app/globals.css`, not generic Tailwind gray/dark-mode
   palettes.

3. **Color carries semantics.**
   Status colors, evaluation state, selection, and snapshot pins are meaningful.
   Decorative color should be rare.

4. **Experiment language only.**
   New user-facing UI must say experiment, run, task, evaluation, and rubric.
   Cohort remains a deleted/deprecated concept and should only appear in tests
   that assert its absence or in historical docs.

5. **The graph is an instrument.**
   The run workspace should feel like one coordinated debugger: graph, task
   workspace, event stream, and activity timeline all respond to selection and
   time consistently.

6. **No black-box scores.**
   Evaluation UI should make criteria, skipped/errored states, aggregation, and
   reasoning visible without overwhelming the default view.

## UX Verification

UX quality is not done when the code compiles or the page "looks better". Each
PR must leave behind evidence that the target product tasks are easier
to complete.

### Required Screenshot Evidence

Every PR that changes a visible surface must include fixed-viewport
screenshots in the PR notes or implementation plan:

- Before and after at desktop viewport `2048x1228`.
- Current target surface next to the relevant archive reference when one
  exists.
- At least one screenshot for the main interaction state, not only the default
  empty or idle state.
- For run workspace changes, include graph-only, drawer-open, and
  timeline-visible states when affected.
- For rubric changes, include a passing criterion, a failing criterion, and an
  errored or skipped state when data exists.

Each screenshot pair must be annotated with concrete deltas:

- What hierarchy became clearer.
- What information moved above the fold or became easier to scan.
- What visual noise was removed.
- What status, selection, live/snapshot, or evaluation state is now more
  legible.

### Product Task Checks

The implementation is not complete until a reviewer can answer these tasks from
the UI without reading raw JSON, logs, or database rows:

- Experiment page: what is this experiment, how many runs passed/failed, which
  run should I inspect first, and why?
- Experiment page: can I compare completed and failed runs without losing
  runtime, score, task, model, or evaluator context?
- Run workspace: is this view live or a snapshot, which task is selected, what
  is blocked, and what changed around this sequence/time?
- Run workspace: can I distinguish completed, failed, blocked, pending, and
  running work at normal zoom?
- Rubric drawer: what score did this task receive, how was it aggregated, which
  criteria drove the result, and what reasoning or error explains it?
- Rubric drawer: are skipped and errored criteria visible as states, not
  silent omissions?

### Visual Checklist

Each PR must pass this checklist before it is considered done:

- Typography is sans-serif and consistent when web fonts are delayed or absent.
- Primary data and primary actions are visible without avoidable scrolling.
- Status color is semantic; decorative color is rare.
- Selection state is obvious and persists across graph, drawer, and timeline
  where relevant.
- Live versus snapshot state is clear.
- Tables and metric tiles use consistent alignment, spacing, and numeric
  formatting.
- Text does not overflow or overlap at the target viewport.
- Empty, loading, and error states are intentionally handled.
- Core surfaces use Ergon tokens rather than generic `gray-*`, `slate-*`, or
  `dark:*` styling.
- No user-facing cohort language appears in current product UI.

### Automated Guardrails

Use automation where the failure mode is objective:

- Run `pnpm -C ergon-dashboard run test:unit`.
- Run the relevant Playwright smoke or screenshot checks for changed pages.
- Add or update tests for formatting helpers, status labels, evaluation labels,
  and empty/error states touched by the change.
- Add a grep or unit assertion for stale `cohort` UI text when changing nav,
  headings, routes, test IDs, or visible copy.
- Verify screenshots do not show serif fallback, broken images, overlapping
  text, blank graph canvases, or missing drawer content.

### Definition Of Done

A PR in this stack is done only when all of the following are true:

1. The code path is implemented against real dashboard data or an explicit
   documented mock boundary.
2. Tests and automated guardrails pass.
3. Before/after screenshots exist for the changed surface.
4. The screenshot annotations explain the UX deltas in concrete terms.
5. The product task checks above are answerable from the UI.
6. Any remaining backend dependency has an owner, target PR or issue, and a
   visible unavailable state in the product surface.

### Reviewer Prompt

Use this prompt for human or LLM review of the PR:

```text
Compare the before/after screenshots against the RFC reference images. Call out
regressions in hierarchy, spacing, typography, semantic color, status
visibility, graph readability, drawer attachment, timeline readability, and
rubric explainability. Do not approve based on aesthetics alone. Approve only
if the target product tasks are easier to complete and the screenshot evidence
shows concrete improvements.
```

## Implementation Plan

Ship this as a stack of small PRs under the umbrella:
**Frontend quality and design system refresh**.

The stack should preserve one visual direction while keeping each reviewable
unit small enough to verify. Every PR in the stack must satisfy the shared UX
Verification section above for the surfaces it touches. Later PRs may refine
shared primitives from earlier PRs, but should not leave a visible surface in a
half-migrated state.

Stack order:

### PR 1: Foundations And Screenshot Baseline

Fix the design-system base and create a visual baseline before page redesigns:

- Repair font fallback declarations:
  `--font: var(--font-inter, Inter), ui-sans-serif, system-ui, ...` and
  `--mono: var(--font-jetbrains-mono, "JetBrains Mono"), ...`.
- Add reusable UI primitives for section labels, cards, metric tiles,
  segmented controls, empty states, and compact data tables.
- Replace generic gray/dark classes in core surfaces with tokenized Ergon
  styles.
- Clean up top navigation so only working product surfaces are exposed:
  remove or hide dead `Models` and `Settings` links until they have real
  destinations. Keep `Runs` visible, but in PR 1 make it a deliberate
  unavailable page that points users back to experiments and says the real
  endpoint-backed runs index lands in PR 5.
- Capture baseline screenshots for the experiment page, run workspace, and
  rubric/evaluation drawer using existing Playwright tooling.

Acceptance:

- Browser screenshots show sans-serif UI typography even when web fonts are
  delayed or unavailable.
- Core pages no longer rely on generic dark-mode Tailwind classes for primary
  surfaces.
- Top navigation contains no dead links. `Experiments` opens the working index,
  `Runs` opens the temporary PR 1 unavailable page, and `Models`/`Settings` are
  hidden until they have product-backed destinations.
- The three comparison surfaces have repeatable screenshot checks or documented
  manual screenshot commands.
- `pnpm -C ergon-dashboard run test:unit` and the relevant screenshot/e2e
  check pass.

### PR 2: Experiment Page Refresh

Make `/experiments/[definitionId]` feel like the control surface for a single
experiment:

- Compact header with benchmark, model, evaluator, sample count, run count,
  latest activity, and status.
- Replace generic cards with stronger summary metrics: score, pass/fail/active
  runs, runtime, cost/errors, average tasks.
- Add a reusable `RunMetricExplorer` visualization component for run-level
  metrics. The goal is not one hardcoded chart; it is a small analytical
  instrument that can adapt to what each experiment measures.
- `RunMetricExplorer` inputs:
  - A list of metric descriptors such as score, duration, task count, tool
    calls, cost, tokens, return, or benchmark-specific values.
  - One metric selection for `1D` mode.
  - Two metric selections for `2D` mode.
  - Run metadata for hover and click behavior.
- `1D` mode shows a distribution for one metric:
  - For fewer than 5 numeric values, show a compact ranked list or run strip
    instead of pretending there is a distribution.
  - For 5-19 numeric values, show a rug/dot strip or simple histogram.
  - For 20+ numeric values, histogram plus summary markers like p50/p95 is
    acceptable.
  - Do not imply a true normal "bell curve" unless the visualization is clearly
    a smoothed density over observed values.
- `2D` mode plots one metric against another:
  - Works from 3+ numeric points.
  - Show "too few points for trend" copy until at least 10 points.
  - Do not ship trendlines/correlation in this PR. Add them later only through
    metric-pair-specific product decisions.
- Data contract:
  - Extend the experiment detail backend contract with a run metric projection
    used by summary cards, the run table, and `RunMetricExplorer`.
  - Add explicit nullable fields for score/return, duration, task count,
    tool-call count, cost, tokens, token breakdown, model, evaluator, sample
    label, status, and error summary.
  - Populate the fields from `RunRecord`, run summaries, graph/task rows,
    evaluations, and context/event rows.
  - Current schema facts:
    - Tool-call count is available by counting `run_context_events` rows with
      `event_type = "tool_call"`.
    - Token IDs are schema-supported on context-event payloads, but current
      smoke data records null token IDs. PR 2 must add write-side persistence
      for provider token usage as well as local token IDs, then aggregate
      totals and semantic breakdowns for prompt/input, assistant output,
      reasoning/thinking, tool-call arguments, tool results, cached tokens, and
      unknown tokens.
    - Cost is not reliable yet. `runs.summary_json.total_cost_usd` exists, but
      the current completion path writes a default `0.0` without observed
      provider/tool-cost instrumentation. PR 2 must fix core cost calculation,
      persist observed provider/tool/sandbox cost inputs, aggregate them into
      run metrics, and mark whether cost is observed so the UI can distinguish
      real zero from unavailable.
- First metric set:
  - Score or return from the run metric projection.
  - Duration from the run metric projection.
  - Task count from the run metric projection.
  - Tool-call count from persisted context events.
  - Tokens from persisted provider usage and context-event token IDs, including
    semantic token breakdowns.
  - Cost from fixed core cost aggregation with an observed-cost marker.
- Default view:
  - For 2-4 runs, show the run health strip/table as the primary view and make
    the explorer secondary.
  - For 5+ runs with score/return and duration values, default the explorer to
    `2D` score or return versus duration.
  - If either selected metric is absent, show the metric as unavailable and use
    the first available numeric pair from the explicit descriptor list.
- Hovering any point or bucket shows all available run meta, not only the
  selected axes: run id/name, status, sample, score/return, duration, task
  count, tool calls, cost, tokens, evaluator, model, and error summary when
  present.
- Clicking a point opens the run workspace.
- Improve the run table with status badges, row-level error treatment, score
  formatting, and quick links to run workspace.
- Add run filtering: all, active, completed, failed.
- Keep useful archive ideas, but rename all cohort-era concepts to experiment
  language.

Acceptance:

- The page explains the experiment at a glance and makes failed/completed runs
  easy to compare.
- Two-run and three-run smoke experiments render without awkward empty space.
- `RunMetricExplorer` degrades gracefully for small experiments and does not
  show misleading distributions or trend claims.
- Hovering a point provides enough context to decide whether to open that run.
- No cohort wording appears in UI text or test IDs.

### PR 3: Run Workspace Composition

Polish the debugger experience without changing core behavior:

Reference images:

- Current: `assets/current-run-workspace.png`
- Archive target: `assets/archive-run-workspace.png`

- Tighten the run header so status, live/snapshot state, task counts, score,
  and actions form one coherent strip.
- Fix run header metric readouts for tasks, tokens, cost, and score:
  - Show real values whenever backend data exists.
  - Use deliberate empty states when a value is absent, not a visually ambiguous
    dash that looks broken.
  - Format score, cost, tokens, and task counts consistently across run
    workspace, experiment detail, and run index.
  - Style the metric strip so values are scannable and not washed out compared
    with the page title or action buttons.
- Tune graph canvas spacing, minimap placement, controls, and legend so they
  do not compete with the task workspace.
- Make the task workspace drawer feel attached to the selected node/time:
  stronger header hierarchy, clearer selected sequence badge, better close and
  resize affordances.
- Make the timeline read as a supporting trace: compact labels, stable
  vertical rhythm, clearer now/snapshot distinction.
- Match the archive mockup's visual discipline where it helps: slim controls,
  quiet container frames, stable graph spacing, consistent node sizing,
  restrained borders, and clear selected-state treatment.
- Keep the graph, drawer, and timeline visually coordinated. They should read
  as one debugger surface, not three stacked widgets.
- Reuse `RunStatusBar` or retire it; do not keep unused UI primitives around.

Acceptance:

- Selecting a graph node and selecting a timeline activity both produce a
  visually obvious, coherent state.
- The run header makes task count, tokens, cost, and score either visible and
  correctly formatted or explicitly unavailable.
- The failed smoke run path remains readable: failed task, blocked downstream
  task, and completed sibling work are easy to distinguish.
- The before/after screenshots show reduced visual clutter in controls,
  stronger graph/drawer/timeline alignment, and no overlap between toolbar,
  graph, minimap, drawer, and timeline.
- Node labels, status pills, metric labels, and toolbar controls remain legible
  at the target desktop viewport.

### PR 4: Rubric Drawer And Evaluation Visibility

Port the best old eval-visibility ideas into current UI:

Reference images:

- Current: `assets/current-rubric-drawer.png`
- Archive target: `assets/archive-rubric-drawer.png`

- Replace the heavy graph `R` badge with a quieter indicator:
  status-dot ring, small inline glyph, or a tokenized evaluation marker.
- Keep evaluation lens mode as a first-class graph control.
- Upgrade the evaluation drawer/panel to use Ergon tokens and show:
  evaluator, aggregation rule, normalized score, total/max score,
  criterion statuses, contribution, reasoning, input, skipped reason, and
  error details.
- Match the archive drawer's information hierarchy: rubric summary first,
  contribution/score composition next, then compact criterion rows, with one
  expanded criterion showing inputs, reasoning, metadata, and error/skipped
  details.
- Show skipped/errored criteria as explicit states, not missing data.
- Defer row-level rubric coverage strips on experiment detail until a dedicated
  `RunRubricCoverageDto` exists. Do not infer coverage by scraping drawer
  labels or raw JSON.

Acceptance:

- A low score is explainable from the UI without raw JSON spelunking.
- Failed/skipped evaluation paths are visible and honest.
- Evaluation markers do not clutter the graph at normal zoom.
- The drawer screenshot shows clear hierarchy between task context, evaluation
  summary, criterion list, expanded criterion detail, and actions.
- Pass/fail/skipped/error states use distinct semantic treatments without
  turning the drawer into a noisy color block.

### PR 5: Experiment And Run Index Follow-Up

After the three screenshot-backed surfaces are improved, upgrade the index
pages so navigation feels as mature as inspection.

Reference images:

- Experiment detail target pattern: `assets/archive-experiment-page.png`
- Current experiment page for comparison: `assets/current-experiment-page.png`

Upgrade `/experiments` from a plain table into the top-level operational
surface:

- Add compact filter/sort controls for status, benchmark, activity, score, and
  run count.
- Show run count, average score, failure count/rate, runtime/last activity,
  status, default model, and evaluator in a scan-friendly table.
- Use status badges and mono numeric cells consistently.
- Keep the page empty state useful and direct: no experiments, API error, and
  stack unavailable should read differently.
- Match the archive table density where appropriate: compact rows, strong
  column alignment, clear status pills, muted secondary text, and metric cells
  that can be scanned quickly.

Build the real `/runs` page using the same dense operational table pattern:

- Add the paginated/filterable backend `/runs` list endpoint and replace the PR
  1 unavailable page with a real run index.
- Show experiment, sample, status, duration, score, tasks, model, evaluator,
  and latest activity.
- Link into run workspace and experiment detail.
- Use the same table, badge, metric, empty/error, and filter primitives as the
  experiment index so the two index pages feel like one navigation system.

Acceptance:

- The experiment index answers: what is running, what failed, what changed
  recently, and what should I open next.
- Users can find a run without starting from an experiment detail page.
- Backend support for the run index is implemented in this PR through the
  `/runs` list endpoint and matching frontend server-data loader.
- Index screenshots show consistent row height, column alignment, badge style,
  numeric formatting, search/filter controls, and empty/error treatment.
- Clicking the `Runs` nav item has an obvious outcome and never depends on
  first navigating through an experiment detail page.

### PR 6: Archive Cleanup And Quality Rules

Close the loop so the old archive remains useful without confusing future
implementation:

- Decide whether `ergon_fe_design_system` stays as a local archive, moves into
  docs screenshots, or is deleted after the useful patterns are ported.
- Add explicit frontend quality invariants to dashboard architecture docs if
  accepted.
- Add an LLM-facing note that future frontend work should compare against the
  screenshot-backed surfaces and use tokenized primitives.

Acceptance:

- The useful archive lessons live in repo docs or implemented product code.
- Stale cohort-era archive vocabulary is not treated as current product
  vocabulary.
- Future agents have a natural place to learn the dashboard visual rules.

## What To Keep From The Old Design Archive

Useful:

- Surface/status/accent token philosophy.
- Dense table patterns.
- Compact status pills and mono numeric cells.
- Experiment detail health summary plus run list composition.
- Graph + task workspace + activity timeline composition.
- Eval/rubric visibility explorations, especially quieter badge alternatives
  and skipped/errored-state visibility.
- Motion notes for node selection, drawer open, and event-to-snapshot.

Do not port directly:

- Cohort vocabulary, routes, IDs, or CTAs.
- Training/model/settings aspirations unless separately specified.
- Static deck scaffolding (`deck-stage.js`) into product code.
- Decorative mock-only copy or chart data.

## Invariants Affected

This RFC does not change backend data or runtime invariants. It adds frontend
quality invariants:

- User-facing dashboard language uses experiments, not cohorts.
- Core dashboard surfaces use Ergon tokens for color, typography, borders, and
  shadows.
- Evaluation state is visible as structured UI, not only raw payloads.
- Visual regressions on key dashboard surfaces should be caught by screenshot
  or e2e checks.

## Migration

No database migration is required.

Frontend migration should be incremental:

1. Add or repair shared primitives.
2. Move one page or component at a time to tokenized styles.
3. Keep existing data contracts stable unless a PR explicitly changes them.
4. Update Playwright smoke expectations when labels, test IDs, or visual
   affordances intentionally change.
5. Remove unused primitives and stale cohort-era docs only after equivalent
   experiment-language docs exist.

## Alternatives Considered

### Port the old design system wholesale

Rejected. It contains useful visual direction, but its product vocabulary is
stale and cohort-centered. A wholesale port would revive concepts we just
deleted.

### Only fix the font bug

Rejected as insufficient. The font issue is likely a large visual multiplier,
but page hierarchy, density, evaluation UI, and token consistency still need
work.

### Rewrite the dashboard from scratch

Rejected. The current app already has valuable infrastructure: live run state,
graph layout, task workspace, event stream, activity timeline, generated
contracts, and smoke tests. The right move is focused visual and interaction
refinement.

### Defer all polish until backend APIs settle

Rejected. Most of the quality problems are frontend composition issues and can
be improved against existing contracts. Backend-dependent pieces, like a full
runs index or richer rubric coverage strips, should be called out explicitly.

## Open Questions

- Which evaluation marker should become the default: status-dot ring, inline
  glyph, or a small tokenized badge?
- Should experiment detail include a compact score/runtime chart, or is a
  run-health strip enough for small smoke experiments?
- Should rubric drawer actions such as "re-run rubric" be visible but disabled
  until backend endpoints exist, or hidden until real behavior is wired?
- Should `/runs` wait for the paginated runs API RFC, or ship against the
  current available data first?
- Do we want to maintain `ergon_fe_design_system` as an archive, or move the
  good screenshots into this RFC and delete the folder later?

## On Acceptance

When this RFC is accepted:

- Use the stack-level implementation plan under
  `docs/superpowers/plans/frontend-quality-refresh/`, which lists PRs 1-6,
  dependencies, screenshots, and UX verification evidence expected for each PR.
- Update `docs/architecture/05_dashboard.md` with the frontend quality
  invariants if they are accepted as architecture-level rules.
- Add screenshot/e2e acceptance checks for the experiment detail and run
  workspace.
- Decide whether `ergon_fe_design_system` remains an archive or is migrated
  into repo docs and deleted.
