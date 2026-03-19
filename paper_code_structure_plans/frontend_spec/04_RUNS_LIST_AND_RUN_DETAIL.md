# Runs List And Run Detail

## Runs List

### Purpose

The runs list is the triage surface.

It should help a user answer:

- which runs matter right now?
- which runs are still executing?
- which runs failed?
- which run should I inspect next?

For the default product shape, this runs list usually sits inside an experiment cohort page.

### Expected Visible Fields

Each run row or card should expose enough information to orient the user.

At minimum:

- run identity
- benchmark name
- overall run status
- a minimal timing signal

Optional but often helpful:

- score summary
- final updated time
- top-level error summary for failed runs
- running time so far for active runs

### Status Semantics

The runs list must clearly distinguish:

- pending
- running
- completed
- failed

Users should not need to infer status from vague color alone.

### Live Signals On The Runs List

The runs list should be able to reflect lightweight live change without requiring the user to open every run.

Useful signals include:

- run status transition
- updated timestamp
- score arrival
- failure summary arrival

The runs list should not attempt to show full task evidence.

It should remain a triage surface.

### Interaction

Clicking a run should:

- open that run's detail page or panel
- preserve enough navigation context to return to the list

The preferred navigation affordance is:

- a breadcrumb back to the cohort page

## Run Detail

### Purpose

The run detail surface is the main inspection page.

It should unify:

- run summary
- graph view
- selected task workspace view
- final outputs and evaluation where relevant

It should also expose:

- a secondary raw-events drawer or panel for exact chronological inspection

### Internal Regions

The run detail surface should have clearly differentiated regions.

At minimum:

- breadcrumb back to cohort
- run header
- graph view
- workspace view

The workspace view should have named subsections or tabs for:

- overview
- executions
- actions
- communication
- outputs
- evaluation

The workspace should default to:

- outputs and artifacts as the primary pane when present

If the selected task does not yet have outputs, the primary workspace pane should fall back dynamically to the most meaningful evidence for the task state.

This is intentionally closer to a focused workspace than to a thin inspector panel.

The user should feel like they are:

- scanning the graph on one side
- working through the selected task's evidence on the other

### Run Summary

The top of the run detail should show:

- run identity
- benchmark
- overall status
- timing
- high-level score or failure summary if present

It should also be the place where the UI communicates:

- stale or disconnected live-update state
- whether the run is still actively changing

It may also include:

- enough cohort context to remind the user which experiment cohort they came from

### Relationship To The Graph

The run detail should treat the graph as structural context.

The graph should answer:

- what tasks exist?
- what depends on what?
- what state is each task in?

The graph should not be the only source of evidence.

The graph view should stay optimized for:

- scanability
- status comprehension
- topology comprehension
- rapid task switching

### Relationship To The Detail Pane

The selected task detail should answer:

- what happened inside this task?
- why is it in this state?
- what evidence supports that?

The run detail page should make the graph and detail pane feel like two views of the same truth.

The workspace view should stay optimized for:

- evidence density
- chronology
- communication visibility
- output inspection
- retry and execution clarity

## Where Different Update Types Appear

The run detail screen should make update routing obvious.

### Run Status Updates

Should appear in:

- runs list
- run header

### Task Topology Changes

Should appear in:

- graph region

They may also trigger:

- selection validation
- a small structural-change notice if needed for comprehension

### Task Execution Updates

Should appear in:

- graph node status
- workspace overview
- workspace executions section

### Action Updates

Should appear in:

- workspace actions section of the selected task
- optional summary counters in workspace overview

### Communication Updates

Should appear in:

- workspace communication section of the selected task

They should not be visually conflated with tool actions.

### Output Updates

Should appear in:

- workspace outputs section of the selected task
- run summary if they affect the final run artifact set

### Evaluation Updates

Should appear in:

- workspace evaluation section of the selected task if task-scoped
- run header if run-scoped

## Required Behavior For Partial Visibility

If a task is not selected, the graph should still surface that change happened.

Examples:

- node status changed
- node failed
- node was added to the graph

The full evidence can remain in the detail pane for the selected task.

## Required Invariants

- run detail must reflect the run the user actually selected
- selected task detail must match the selected node
- terminal run detail must not still look live
- running run detail must not claim terminal completion too early
- the breadcrumb path back to the cohort must remain correct
