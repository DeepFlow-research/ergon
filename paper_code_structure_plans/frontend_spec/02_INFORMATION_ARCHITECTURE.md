# Information Architecture

## Top-Level Screens

The frontend should have a small number of high-value surfaces.

### Experiment Cohort View

Purpose:

- act as the main operations surface for many runs
- monitor live progress across a named cohort
- expose aggregate progress and status counts
- provide entry into individual runs

This should be the top-level object in the product model.

### Runs List

Purpose:

- give an overview of recent and relevant runs
- support triage
- support entry into run detail

In practice, the default runs list should usually live inside a cohort context rather than as a detached global page.

### Run Detail

Purpose:

- show one run as the main debugging unit
- combine run summary, task graph, and selected task detail

### Optional Secondary Surfaces

Only add dedicated secondary screens if they materially reduce confusion.

Examples:

- output artifact viewer
- evaluation detail modal or panel
- event/log stream panel

These should remain subordinate to the run detail experience.

One especially useful secondary surface is:

- a raw events drawer on the run page

## Main Data Layers

The UI should conceptually separate:

- run-level data
- task-level data
- task-execution data
- action-level data
- communication data
- output/resource data
- evaluation data
- live update/event data

### Run-Level Data

Includes:

- run identity
- benchmark
- overall status
- timing
- high-level score or summary

At cohort level, mixed benchmarks are valid, so benchmark identity should remain visible per run.

### Task-Level Data

Includes:

- task identity
- task status
- parent/child or dependency placement in the graph
- selected-task context

### Task-Execution Data

Includes:

- execution attempt identity
- execution start and end time
- execution status
- retry or re-execution history
- the currently active execution for a task

### Action-Level Data

Includes:

- ordered tool or worker actions
- inputs and outputs where useful
- action timing
- action failure details

### Communication Data

Includes:

- agent messages
- stakeholder questions
- stakeholder answers
- system notices that materially affect user understanding

### Output Data

Includes:

- final artifacts
- output file names
- output availability and location

### Evaluation Data

Includes:

- run-level summary
- task-level results where applicable
- criterion-level detail when useful for debugging

### Cohort-Level Data

Includes:

- cohort identity
- reproducibility metadata
- run counts by status
- aggregate duration and score summaries
- live cohort progress

Useful reproducibility metadata may include:

- code commit or snapshot identifier
- worker or prompt version
- model or provider version
- tool or sandbox configuration snapshot

## Run Detail Layout

The run detail screen should have a stable internal layout.

At minimum it should contain:

- a breadcrumb back to the cohort view
- a run header for summary state
- a graph view for structure
- a workspace view for evidence

The workspace view should be able to expose:

- task overview
- execution history
- action stream
- communication thread
- outputs
- evaluation

This can be implemented with sections, tabs, or stacked panels.

The important part is that each data type has a predictable home.

## Dual-Surface Model

The main run screen should follow a dual-surface model.

The full product hierarchy should be:

1. cohort view
2. run detail
3. selected task workspace

### Graph View

The graph view is the structural surface.

It answers:

- what tasks exist?
- how are they related?
- where is work currently happening?
- where is failure concentrated?

This surface should stay visually lightweight enough to scan quickly.

### Workspace View

The workspace view is the evidence surface for the selected task.

It answers:

- what is this task doing right now?
- what happened in its current or past executions?
- what tools ran?
- what messages were exchanged?
- what outputs were produced?
- how was it evaluated?

This surface can be denser, because it is for focused inspection rather than global scanning.

## Workspace View Structure

The workspace view should feel like a compact debugging workspace rather than a generic sidebar.

Useful structure:

- a workspace header with task name, current status, and key summary signals
- a primary content area for outputs or main evidence
- secondary sections or tabs for executions, actions, communication, and evaluation

The important design idea is:

- graph view gives context
- workspace view gives proof

## Surface Ownership

The frontend should make it obvious where each kind of information lives.

### Runs List Owns

- run identity
- run status
- benchmark identity
- high-level triage signals

### Cohort View Owns

- cohort identity
- cohort reproducibility metadata
- counts by run status
- aggregate progress across many runs
- clickable run list inside the cohort

### Run Header Owns

- current run status
- top-level timing
- score or failure summary
- connection or staleness indicators for the currently viewed run

### Graph Owns

- task topology
- task status at a glance
- selection state
- structural progress across the run

### Task Detail Owns

- the evidence for the selected task
- execution attempts
- ordered actions
- communication history
- outputs and artifacts
- evaluation detail

## Live Update Routing

The frontend should route different update types to different surfaces.

At a minimum:

- run-level status changes affect the runs list and run header
- topology changes affect the graph and task selection validity
- execution changes affect the graph and task overview
- action changes affect the selected task's action stream and summary counters
- communication changes affect the selected task's communication section
- output changes affect the selected task's outputs section and possibly run summary
- evaluation changes affect evaluation sections and high-level score summaries

## Primary Navigation Model

The intended navigation loop is:

1. user opens an experiment cohort
2. user monitors many runs and summary stats
3. user selects a run
4. user sees run detail
5. user selects a task from the graph
6. user inspects actions, outputs, and evaluation in the task detail pane

This should be the default debugging flow.

## Core Selection Rules

Selection state should be explicit and stable.

The UI should maintain:

- selected run
- selected task within that run

The detail pane must always correspond to the currently selected task.

If the selected task disappears or becomes invalid:

- selection should reset explicitly
- the UI should not silently show stale detail from another task

## Data Ownership Expectations

The frontend should treat backend data as the source of truth.

The frontend should own:

- rendering
- selection
- local view state
- event application

The frontend should not invent domain truth beyond what is needed for presentation.
