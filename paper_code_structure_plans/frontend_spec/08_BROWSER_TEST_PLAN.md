# Browser Test Plan

This document derives the browser suite from the frontend behavior spec.

## Principle

Browser tests should prove:

- the UI reflects backend truth correctly
- the UI updates correctly when truth changes

Browser tests should not become the place where product behavior is invented.

For v1, the highest browser priority is:

- cohort-to-run truth first
- deep single-run correctness immediately after

The cohort layer should be specified early, and the run page should earn correctness before the browser suite expands broadly into mixed-benchmark cohort comparisons.

## Test Layers

### Seeded-State Tests

These are the default.

They should validate:

- rendering correctness
- graph/detail binding
- terminal-state visibility
- failure-state visibility
- output and evaluation visibility

### Controlled-Event Tests

These should validate:

- status transitions
- incremental updates
- topology reconciliation
- execution-attempt updates
- stale-state replacement
- action append behavior
- communication append behavior
- output-availability updates
- evaluation-arrival updates

### Tiny Live Probes

These should validate:

- end-to-end wiring still works

They should not carry most coverage.

## Testing Stack

The intended frontend test stack should be:

- `Playwright` as the primary frontend correctness framework
- optional `Vitest` only for small pure-client unit tests
- backend-backed seeded fixtures for most browser tests
- a very small number of real live probes for full wiring checks

### Primary Tool: `Playwright`

Use `Playwright` for the browser suite because the core product risks are:

- route-to-route correctness
- cohort row to run page navigation
- graph and workspace rendering in a real browser
- live update behavior
- stale connection handling

This suite is fundamentally about browser-visible product truth, not isolated component behavior.

### Secondary Tool: `Vitest`

`Vitest` is optional and should only be used where a browser is unnecessary.

Good candidates:

- pure state-store merge logic
- selector helpers
- tiny formatting or mapping helpers

Do not let `Vitest` become the primary confidence layer for:

- routing correctness
- graph selection correctness
- workspace evidence rendering
- live-update UI behavior

Those belong in `Playwright`.

### Do Not Use

For v1, do not introduce:

- `Cypress`
- a second browser E2E framework
- heavy component-test infrastructure that duplicates browser coverage

The goal is one clear browser stack, not multiple partially-overlapping ones.

## Planned Repo Shape

A mid-level engineer implementing this plan should create a predictable FE test layout.

Recommended structure inside `arcane-dashboard/`:

```text
playwright.config.ts
tests/
  e2e/
    cohort.snapshot.spec.ts
    run.snapshot.spec.ts
    run.live.spec.ts
    raw-events.spec.ts
  fixtures/
    cohort-snapshot/
    run-snapshot/
    controlled-delta/
  helpers/
    routes.ts
    selectors.ts
    seeded-state.ts
    event-driver.ts
```

The exact filenames can vary, but the responsibilities should remain separated:

- spec files describe user-visible behavior
- fixture files define persisted snapshot state and controlled delta streams
- helper files hide low-level setup and selector mechanics

## Playwright Responsibilities

The `Playwright` layer should own:

- page navigation
- assertions against visible UI
- browser interaction
- timing and waiting discipline
- controlled live-update assertions

The `Playwright` layer should not own:

- complex fixture synthesis logic hidden inline in tests
- business-state invention
- backend truth modeling that should live in shared fixture builders

## Fixture Strategy

Most tests should not boot the full real stack from scratch.

The default path should be:

1. seed deterministic backend fixture state
2. open the relevant FE route in Playwright
3. assert snapshot truth
4. optionally drive controlled deltas

This keeps failures:

- fast
- deterministic
- explainable

### Fixture Source Of Truth

Fixture data should come from backend-shaped truth, not handcrafted FE-only JSON invented in the browser tests.

Preferred sources:

- persisted DB state created by backend helpers
- DTO-shaped API fixtures derived from backend contracts
- controlled event payloads shaped from real backend event contracts

Avoid:

- browser tests inventing ad hoc fake domain models
- copying API payloads into many spec files
- snapshot fixtures that drift away from backend semantics

## Environment Modes

The plan should explicitly support three FE test environment modes.

### Mode A: Snapshot Mode

Used for the majority of tests.

Characteristics:

- deterministic persisted state
- no real live event dependency
- fastest and most reliable mode

Used for:

- cohort page snapshot truth
- run header truth
- graph truth
- workspace evidence truth
- failure-state truth

### Mode B: Controlled Delta Mode

Used for live-update correctness without depending on the full real runtime.

Characteristics:

- starts from snapshot mode
- injects controlled event deltas in a known order
- asserts state merges correctly

Used for:

- run status transitions
- action and message append behavior
- topology changes
- stale/reconnect behavior

### Mode C: Tiny Live Probe Mode

Used only for a few smoke checks.

Characteristics:

- runs against the real stack
- uses the real `magym benchmark run ... --cohort-name ...` flow or equivalent live setup
- low count and low ambition

Used for:

- "page loads against the real stack"
- "one real update reaches the UI"

This mode should never carry most FE coverage.

## Implementation Rules

To keep the plan executable by a mid-level engineer, the following rules should be treated as part of the spec:

- prefer `data-testid` or similarly stable selectors for critical graph, run-row, and workspace assertions
- avoid CSS-structure selectors for important assertions
- every Playwright test should declare which fixture mode it uses
- every controlled-delta test should name the ordered events it injects
- every live probe should justify why snapshot or controlled-delta mode was insufficient
- browser tests should assert user-visible semantics, not internal implementation details
- do not add broad screenshot-golden testing as the primary correctness mechanism

## First Setup Work

Before implementing the first FE browser test, the engineer should complete this setup checklist:

1. add `Playwright` to `arcane-dashboard`
2. create `playwright.config.ts`
3. add an `e2e` test script in `arcane-dashboard/package.json`
4. create a small fixture harness for snapshot mode
5. create stable selectors on cohort rows, run header, graph nodes, and workspace sections
6. prove one trivial Playwright test can open the dashboard route successfully

Only after that should the first real browser behavior test be written.

## First Test Set

The first FE browser test wave should prove the product hierarchy:

1. cohort page is trustworthy
2. cohort row navigation opens the right run
3. run page renders graph truth correctly
4. selected task workspace renders evidence correctly

The first single test should be:

### `test_run_graph_matches_seeded_dag`

Why first:

- wrong run or task identity is one of the most dangerous failure modes
- if the graph cannot render seeded topology correctly, the graph-workspace contract is already broken

## V1 Browser Waves

### Wave 1: Cohort Snapshot Truth

Start with the cohort because it is now the top-level operator surface.

Priority tests:

### `test_cohort_summary_and_run_list_render_snapshot_truth`

Proves:

- cohort header identity is correct
- summary counts match backend truth
- run rows show benchmark, status, and timing context
- mixed benchmark identity is visible per row

Fixture shape:

- one cohort with a small run set
- at least one running row
- at least one completed row
- at least one failed row

### `test_clicking_run_row_opens_matching_run_with_cohort_breadcrumb`

Proves:

- clicking a cohort row opens the correct run page
- run identity matches the clicked row
- breadcrumb back to the cohort remains intact
- navigation does not silently swap the user into a different run

### Wave 2: Run Snapshot Truth

This is the first deep-inspection wave.

### `test_runs_list_renders_seeded_terminal_states`

Proves:

- completed and failed runs render correctly from seeded state

### `test_task_detail_shows_actions_outputs_and_evaluation`

Proves:

- selected task detail is actually useful for debugging

### `test_task_detail_shows_communication_separately_from_actions`

Proves:

- stakeholder and agent communication is visible
- communication is not flattened into the action log
- chronology remains readable

### `test_run_header_surfaces_status_score_and_staleness_state`

Proves:

- run header shows top-level truth clearly
- score or failure summary lands in the right place
- stale/disconnected state is communicated at run scope

### Wave 3: Failure And Retry Truth

This wave proves the UI is useful when something goes wrong.

### `test_failure_detail_surfaces_actionable_error`

Proves:

- failed runs and tasks are diagnosable

### `test_selected_task_shows_execution_attempts_and_retries`

Proves:

- execution history is visible and retries are not flattened away
- the active attempt is identifiable
- action evidence remains attributable to the correct attempt

### Wave 4: Controlled Delta Truth

Only after snapshot truth is stable should the suite move onto live updates.

### `test_live_update_transitions_running_to_completed`

Proves:

- running state can advance to completed without stale UI

### `test_live_update_transitions_running_to_failed`

Proves:

- running state can advance to failed without contradictory UI

### `test_selected_task_identity_never_drifts_from_visible_detail`

Proves:

- graph selection and detail pane stay in sync

### `test_topology_update_adds_new_node_without_breaking_selection`

Proves:

- dynamic graph changes preserve task identity and selected detail binding

### `test_new_action_appends_to_selected_task_timeline`

Proves:

- tool progress is rendered as an ordered action stream

### `test_agent_and_stakeholder_messages_render_in_communication_section`

Proves:

- communication is visible and visually distinct from tool actions

### `test_output_arrival_updates_outputs_section_without_full_refresh`

Proves:

- newly available artifacts become visible in the correct task context

### `test_evaluation_arrival_updates_judgment_surfaces_at_the_right_scope`

Proves:

- evaluation appears in task or run scope without landing in the wrong place

### `test_stale_connection_state_is_visible_to_the_user`

Proves:

- the UI distinguishes "no new updates" from "view may be stale"

### `test_raw_events_drawer_shows_filtered_stream_with_raw_toggle`

Proves:

- chronological event evidence is available without becoming the primary UI

## Fixture Recipes

The browser suite should standardize a small set of fixture recipes instead of inventing one-off setups per test.

### Fixture Recipe A: Snapshot Cohort Fixture

Use for:

- cohort summary tests
- cohort run list tests
- navigation into a run

Recommended source:

- persisted DB fixture created from backend state helpers

Reason:

- fast
- deterministic
- enough for snapshot truth without depending on full live wiring

### Fixture Recipe B: Snapshot Run Fixture

Use for:

- graph rendering
- task workspace rendering
- outputs and evaluation rendering
- failure-state rendering

Recommended source:

- persisted DB fixture with one run, one task tree, actions, executions, outputs, evaluation, and optional communication

### Fixture Recipe C: Controlled Delta Fixture

Use for:

- run status transitions
- topology deltas
- action/message/output/evaluation append behavior
- stale or reconnect handling

Recommended source:

- snapshot fixture plus controlled event stream shaped from backend event contracts

### Fixture Recipe D: Tiny Live Probe

Use for:

- proving the real stack still loads and updates at least once

Recommended source:

- real `magym benchmark run ... --cohort-name ...` flow

Keep this tiny and low in count.

## Update Family Coverage

The browser suite should cover each important update family directly:

- run status changes
- topology changes
- execution changes
- action changes
- communication changes
- output changes
- evaluation changes
- staleness and reconnection changes

## Fixture Sources

The browser suite should use:

- seeded DB state shaped from backend deterministic test patterns
- controlled event streams shaped from backend event contracts

This keeps the browser suite aligned with backend truth rather than inventing parallel fixtures.

## Backend Fixture Setup Notes

The frontend test suite should respect the backend distinction between seeded benchmark definitions and real executions.

- `magym benchmark seed ...` should be treated as experiment-definition setup only
- seed flows create `Experiment` data and input resources, not `Run` rows
- cohort pages, run rows, and cohort metrics should therefore be backed by real execution flows, not seed-time placeholders

For frontend tests:

- use seed flows when the fixture only needs benchmark definitions
- use `magym benchmark run ... --cohort-name ...` when the fixture needs real `Run` and `ExperimentCohort` state

The current unified `magym` cohort-run command now has two execution modes:

- workflow-factory launch for `smoke_test`
- seeded-experiment launch for `minif2f` and `researchrubrics`

That means FE fixtures can choose between:

- `magym benchmark run smoke_test --workflow ... --cohort-name ...` when a named synthetic workflow is the cleanest fixture
- `magym benchmark run minif2f|researchrubrics --task-id ... --cohort-name ...`
- `magym benchmark run minif2f|researchrubrics --limit N --cohort-name ...`

For dataset-driven fixture setup, prefer the seeded-experiment path because it exercises the real operator model the FE is supposed to present: reusable `Experiment` definitions and cohort-backed `Run` rows created later from those definitions.

Recommended benchmark use by wave:

- use `smoke_test` for the earliest graph/workspace snapshot tests because it gives compact, predictable DAGs
- use `minif2f` or `researchrubrics` when testing cohort pages that must reflect the real seeded-experiment operator workflow
- use mixed-benchmark cohorts only after single-benchmark cohort correctness is already locked

Mixed-benchmark cohort browser coverage is valuable, but it should come after:

- single-run correctness
- single-benchmark cohort correctness

## Main Failure Interpretation

When seeded-state tests fail:

- suspect rendering, selection logic, or API consumption

When controlled-event tests fail:

- suspect event handling, local state updates, or stale merge logic

When only live probes fail:

- suspect full-stack wiring rather than the dashboard's core render logic

## Later Cohort Coverage

After the run page is stable, the browser suite should add cohort-focused tests for:

- live run-status monitoring across many runs
- mixed-benchmark cohort labeling
- breadcrumb navigation from run page back to cohort
- cohort summary metrics rendering
