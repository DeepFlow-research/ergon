# Browser Test Plan

This document derives the browser suite from the frontend behavior spec.

## Principle

Browser tests should prove:

- the UI reflects backend truth correctly
- the UI updates correctly when truth changes

Browser tests should not become the place where product behavior is invented.

For v1, the highest browser priority is:

- single-run correctness first

The cohort layer should also be specified early, but the run page should earn correctness before the browser suite expands broadly into cohort comparisons.

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

## First Test Set

The first FE browser test should be:

### `test_run_graph_matches_seeded_dag`

Why first:

- wrong run or task identity is one of the most dangerous failure modes
- if the graph cannot render seeded topology correctly, the graph-workspace contract is already broken

### `test_runs_list_renders_seeded_terminal_states`

Proves:

- completed and failed runs render correctly from seeded state

### `test_run_graph_matches_seeded_dag`

Proves:

- graph nodes and edges match seeded topology

### `test_task_detail_shows_actions_outputs_and_evaluation`

Proves:

- selected task detail is actually useful for debugging

### `test_failure_detail_surfaces_actionable_error`

Proves:

- failed runs and tasks are diagnosable

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

### `test_selected_task_shows_execution_attempts_and_retries`

Proves:

- execution history is visible and retries are not flattened away

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
