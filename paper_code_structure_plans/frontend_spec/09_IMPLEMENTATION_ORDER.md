# Implementation Order

This document defines the intended red-green order for the frontend.

## Principle

Start with deterministic, high-signal failures that localize the problem clearly.

Do not start with broad live browser probes.

## Order

### 1. Cohort Snapshot Truth

Goal:

- prove the top-level operator surface before deep run debugging

Minimum tests:

- `test_cohort_summary_and_run_list_render_snapshot_truth`
- `test_clicking_run_row_opens_matching_run_with_cohort_breadcrumb`

Why first:

- the product hierarchy now clearly starts at experiment cohort -> run -> task
- this avoids building a run page that has to be recontextualized later

### 2. Run Header And Runs List Snapshot Truth

Goal:

- prove run-level fetching, routing, and terminal-state rendering

Minimum tests:

- `test_runs_list_renders_seeded_terminal_states`
- `test_run_header_surfaces_status_score_and_staleness_state`

Why first:

- if this fails, the problem is probably very early in FE data flow

### 3. Task Graph Snapshot Truth

Goal:

- prove graph rendering and topology correctness

Minimum tests:

- `test_run_graph_matches_seeded_dag`
- `test_selected_task_identity_never_drifts_from_visible_detail`

Why here:

- once cohort navigation and run header are stable, graph identity becomes the highest-risk structural concern

### 4. Workspace Snapshot Truth

Goal:

- prove selected task evidence rendering

Minimum tests:

- `test_task_detail_shows_actions_outputs_and_evaluation`
- `test_task_detail_shows_communication_separately_from_actions`

### 5. Failure And Retry Snapshot Truth

Goal:

- prove failed and retried tasks remain debuggable

Focus:

- outputs and artifacts are primary when present
- dynamic fallback works when outputs are absent
- retry history remains attributable

Minimum tests:

- `test_failure_detail_surfaces_actionable_error`
- `test_selected_task_shows_execution_attempts_and_retries`

### 6. Controlled-Event Transition Truth

Goal:

- prove live state updates do not corrupt UI truth

Minimum tests:

- `test_live_update_transitions_running_to_completed`
- `test_live_update_transitions_running_to_failed`
- `test_new_action_appends_to_selected_task_timeline`
- `test_agent_and_stakeholder_messages_render_in_communication_section`
- `test_output_arrival_updates_outputs_section_without_full_refresh`
- `test_evaluation_arrival_updates_judgment_surfaces_at_the_right_scope`
- `test_topology_update_adds_new_node_without_breaking_selection`
- `test_stale_connection_state_is_visible_to_the_user`

### 7. Raw Events Drawer Truth

Goal:

- prove chronological debugging evidence is available without polluting the main run workflow

Minimum tests:

- `test_raw_events_drawer_shows_filtered_stream_with_raw_toggle`

### 8. Mixed-Benchmark Cohort Coverage

Goal:

- prove the cohort page remains trustworthy when runs come from different benchmark families

Minimum tests:

- one cohort summary test with mixed benchmark labels
- one navigation test from mixed cohort row to run detail

Why not earlier:

- this is valuable, but it should not be allowed to obscure the simpler single-benchmark failures first

### 9. Tiny Live Browser Probes

Goal:

- prove the real stack still wires together

Minimum probes:

- one cohort page load probe
- one run page load probe
- at most one live update probe

## Red-Green Rules

- write the behavior expectation first
- write the smallest meaningful failing browser test
- make it pass without over-generalizing immediately
- keep tests tied to business-visible state
- use the next failing test to drive the next UI refinement
- do not jump to delta tests before the matching snapshot truth is already locked

## Exit Condition

The frontend should be considered stable enough for broader work when:

- seeded-state tests define the expected behavior clearly
- controlled-event tests prove update correctness
- raw events inspection works as a secondary tool
- live probes are small and mostly boring
