# Browser And Dashboard Tests

This document defines the frontend and dashboard testing strategy.

It should now be read downstream of:

- `paper_code_structure_plans/frontend_spec/00_INDEX.md`

That folder defines the intended product behavior.

This document defines how browser tests should prove that behavior.

It should be treated as a TDD spec for a UI that is currently not reliable.

The point is not:

- "write a few browser tests after the frontend looks healthy"

The point is:

- define the expected dashboard behavior precisely
- write a compact browser suite that matches the repo's testing ethos
- use those tests to identify where the current frontend is broken
- then repair the frontend against that explicit spec

## Goal

Verify that the dashboard shows the correct state, transitions correctly, and stays consistent with backend truth, without depending on full live agent execution for most coverage.

For this slice, the browser suite should answer:

- "If Postgres and dashboard events say the run is in state X, does the UI actually show X?"
- "If the backend emits a meaningful transition, does the UI update in the right order?"
- "If a run completed or failed, can a user actually inspect the evidence they need?"

## Frontend Testing Philosophy

The browser suite should follow the same ethos as the backend deterministic suite:

- very few tests
- strong signal
- deterministic by default
- state-assertive
- minimal live probes only where the external boundary actually matters

This means the default browser input is:

- seeded backend state
- controlled dashboard event streams

not:

- full live backend plus live agents plus live sandbox plus live models

## Primary Oracle

For browser tests, the primary oracle is:

- visible business state in the UI

The supporting oracles are:

- seeded backend state
- controlled dashboard events
- exact run and task identifiers

The key question is:

- "Does the UI faithfully reflect the backend truth a user needs to see?"

If there is a conflict between:

- what the browser renders
- what the seeded state or event stream says should be rendered

the browser is wrong.

## What The Frontend Must Do

Before listing tests, this spec should define the intended user-visible behavior.

### Runs List

Expected behavior:

- the runs list shows the run identity a human actually needs
- each run row shows benchmark, status, and enough timing metadata to orient the user
- completed, failed, pending, and running states are visually distinguishable
- clicking a run opens a detail view without losing the current state context

The tests should be able to answer:

- does a completed run look completed?
- does a failed run look failed for the right reason?
- can the user distinguish a run that is still executing from one that is terminal?

### Run Graph

Expected behavior:

- the graph shows the task nodes for the run
- task edges reflect the real dependency structure
- node statuses match the latest backend truth
- selecting a node reveals the corresponding task details

The tests should be able to answer:

- do the right nodes exist?
- do the right edges exist?
- is each node status correct?
- does node selection actually bind to the correct detail pane?

### Task Detail Pane

Expected behavior:

- the selected task shows its actions in order
- failures show actionable error text
- outputs are visible or linked clearly
- evaluation results are visible when they exist
- stakeholder or communication traces are visible when they matter

The tests should be able to answer:

- can a user inspect what happened for this task?
- can a user understand why it failed?
- can a user see the produced output and evaluation consequences?

### Run Terminal View

Expected behavior:

- completed runs expose final outputs and evaluation summary
- failed runs expose the failure reason and the last meaningful evidence
- terminal pages do not continue to look "live"
- running pages do not claim completion too early

The tests should be able to answer:

- does the page reflect terminal truth correctly?
- are the wrong affordances hidden?
- are the right artifacts and summaries visible?

### Live Update Behavior

Expected behavior:

- status changes appear in the UI in the same semantic order as the backend events
- completion updates replace running state
- failure updates replace running state
- action or log panes append incrementally without corrupting previous content
- the UI does not require a manual refresh to reflect a meaningful event

The tests should be able to answer:

- does the UI react to events correctly?
- does it regress into stale or contradictory state?

## Browser Test Layers

### 1. Seeded-State Browser Tests

These are the default.

Test flow:

1. seed Postgres with a known run/task/action/evaluation shape
2. start backend and dashboard
3. load the page
4. assert the UI reflects the seeded state exactly enough for user-visible correctness

Best for:

- graph rendering
- detail panes
- terminal state rendering
- evaluation visibility
- failed-state visibility
- output artifact visibility

These should be the main frontend debugging layer while the FE is broken.

### 2. Controlled-Event Browser Tests

These start from seeded state and then inject or replay dashboard events.

Best for:

- status transitions
- progressive updates
- log panes
- completion and failure UI changes
- websocket or event-stream rendering logic

These are the second major debugging layer.

### 3. Tiny Live Browser Probes

These are opt-in and minimal.

Best for:

- one real run appears in the UI
- one real run reaches terminal state
- UI state matches DB state for a real run

These are not the main debugging layer.

They exist only to prove the final wiring still holds together.

## Debugging-First Test Order

Because the frontend currently does not work reliably, the intended order is:

1. seeded terminal-state rendering tests
2. seeded detail-pane tests
3. seeded graph-structure tests
4. controlled-event transition tests
5. one or two tiny live probes

That order matters because it helps isolate the failure domain:

- if seeded-state tests fail, the problem is likely in frontend rendering or API consumption
- if seeded-state tests pass but controlled-event tests fail, the problem is likely in event handling or client-side state updates
- if both deterministic layers pass but live probes fail, the problem is likely in full-stack wiring rather than core dashboard behavior

## Required Browser Coverage

### Run List Rendering

Assert:

- expected run rows appear
- statuses match seeded DB state
- benchmark labels render correctly
- terminal and non-terminal runs are visually distinguishable

### Run Graph Rendering

Assert:

- expected nodes appear
- expected edges appear
- statuses match seeded DB state
- node selection changes the visible task detail content

### Task Detail View

Assert:

- action details are visible and ordered
- output artifacts are visible
- evaluation details are visible
- failure messages render correctly
- stakeholder or message traces render when the fixture contains them

### Terminal State Pages

Assert:

- completed runs look completed
- failed runs surface clear reasons
- loading or running states do not show terminal affordances too early
- terminal pages expose the right outputs and evaluation summaries

### Live Update Behavior

Assert:

- task status transitions appear in order
- run completion state appears when expected
- failure updates replace running state correctly
- incremental action history appears without duplication or corruption

### Backend Truth Consistency

Assert:

- the run shown in the UI matches the seeded or queried backend run
- selected task detail content matches the correct task ID
- visible output and evaluation sections correspond to the correct run and task

This matters because a visually plausible dashboard can still be wrong if it binds the wrong data.

## TDD Fixture Set

The fixture set should be intentionally small and strong.

Create seeded fixtures for:

- single-task success with one output artifact and one evaluation summary
- multi-task DAG success with distinct node states and a clear dependency graph
- task failure with action history and explicit error details
- run with evaluation results visible at both task and run level
- run with stakeholder trace or communication history
- run with partial action history while still executing

Create controlled event streams for:

- pending -> running -> completed
- pending -> running -> failed
- action history append while task is running
- run completion event after the last task completes

These fixtures should be shared, compact, and named by user-visible scenario rather than implementation detail.

## Recommended Test Set

The browser suite should start with a handful of tests like these.

### `test_runs_list_renders_seeded_terminal_states`

Purpose:

- prove the main runs list can render completed and failed runs correctly from seeded DB state

Assert:

- run labels, benchmark labels, and statuses are correct
- failed runs show a visible failure indicator
- completed runs show a visible completion indicator

### `test_run_graph_matches_seeded_dag`

Purpose:

- prove graph rendering is faithful to the seeded task tree

Assert:

- expected nodes exist
- expected edges exist
- node statuses are correct

### `test_task_detail_shows_actions_outputs_and_evaluation`

Purpose:

- prove the main task detail pane shows what a user needs for debugging

Assert:

- actions are shown in order
- output artifacts are visible
- evaluation summary or criterion detail is visible

### `test_failure_detail_surfaces_actionable_error`

Purpose:

- prove a failed task is actually debuggable in the UI

Assert:

- failure reason is visible
- the last relevant action or log evidence is visible
- the page does not incorrectly render completion affordances

### `test_live_update_transitions_running_to_completed`

Purpose:

- prove event-driven updates work for the happy path

Assert:

- run or task starts in running state
- completion event changes the visible state correctly
- terminal affordances appear only after completion

### `test_live_update_transitions_running_to_failed`

Purpose:

- prove event-driven updates work for the failure path

Assert:

- running state is replaced by failed state
- failure reason appears
- stale running affordances disappear

### `test_selected_task_identity_never_drifts_from_visible_detail`

Purpose:

- catch common frontend state bugs where selected-node UI and detail pane get out of sync

Assert:

- selecting node A shows task A detail
- selecting node B shows task B detail
- the pane does not show mixed or stale data from another node

## Suggested File Layout

```text
tests/browser/
├── test_runs_list.spec.ts
├── test_run_graph.spec.ts
├── test_task_detail.spec.ts
├── test_failure_rendering.spec.ts
├── test_live_updates.spec.ts
├── test_identity_consistency.spec.ts
└── fixtures/
    ├── seeded-runs.ts
    ├── seeded-dags.ts
    └── event-streams.ts
```

Exact filenames can differ, but the test intent should stay recognizable.

## What Browser Tests Should Assert

Prefer:

- visible graph structure
- visible action, output, and evaluation detail
- status transitions
- identity and consistency between UI and backend truth
- user-visible debugging evidence

Avoid:

- deep implementation details of frontend internals
- large brittle DOM snapshots
- asserting CSS trivia unless it changes meaning
- using browser tests to validate behavior that is already better asserted in backend state tests

## Relationship To Backend State Tests

The browser suite should not try to re-prove all backend correctness.

Instead:

- backend deterministic state tests prove the truth of persisted state
- browser tests prove that the UI reflects that truth

This means browser fixtures should often be built from the same seeded state patterns described in the backend specs.

When a browser test fails, the team should be able to ask:

- is the backend truth wrong?
- or is the UI failing to render or update against correct truth?

The docs and fixtures should make that distinction obvious.

## Live Browser Probe Constraints

If a live browser probe exists, keep it:

- singular or near-singular
- explicit
- smoke-oriented
- focused on end-to-end wiring, not broad state coverage

The point is confidence that the whole loop still wires together, not broad coverage.

## Anti-Patterns

Avoid:

- broad live dashboard E2E runs as the main frontend confidence loop
- full live agent runs just to test a run detail pane
- brittle whole-page snapshot testing
- browser tests that only assert "page loaded" or "no exception was thrown"
- mixing multiple unrelated UI behaviors into one giant browser test

## Acceptance Criteria

This slice is complete when:

- the expected frontend behavior is specified clearly enough that a broken dashboard can be debugged against the doc
- the first browser tests are seeded-state and controlled-event tests, not broad live E2E runs
- most dashboard regressions are caught by seeded-state and controlled-event tests
- only a tiny number of live browser probes remain
- browser tests assert business-visible state, not incidental DOM structure
- a failing browser test makes it clear whether the likely defect is rendering, event handling, or full-stack wiring
