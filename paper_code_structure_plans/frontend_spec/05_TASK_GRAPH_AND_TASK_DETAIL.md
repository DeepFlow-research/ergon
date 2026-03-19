# Task Graph And Task Detail

## Task Graph

### Purpose

The graph provides structure.

In the intended layout, this is the `Graph View`.

It should help a user answer:

- what tasks exist?
- how are they related?
- what state is each one in?

### Expected Behavior

The graph should:

- render the expected task nodes
- render the expected dependency edges
- show current task status on each node
- make the selected node visually obvious

It should also be able to reflect:

- newly added tasks
- newly added dependency edges
- retry or re-execution state at the task level
- failure concentration in one area of the graph

### Identity Requirement

Each node must map stably to one task identity.

This matters most when:

- the graph rerenders
- statuses change
- new tasks or edges appear
- the user changes selection repeatedly

The frontend must never let the graph and detail pane silently point at different tasks.

### Graph Visual Semantics

The graph should communicate different meanings with different treatments.

At minimum:

- pending tasks should look inactive but not failed
- running tasks should look active
- completed tasks should look stable and resolved
- failed tasks should look urgent and easy to spot
- selected tasks should have a stronger selection treatment than mere status styling

If topology changes while the user is watching:

- new nodes should be visually introduced without looking like pre-existing nodes that changed identity
- new edges should appear without causing the user to lose orientation

## Task Detail Pane

### Purpose

The detail pane is the evidence surface for the selected task.

In the intended layout, this is the `Workspace View`.

It should help a user answer:

- what did this task do?
- what tools ran?
- what outputs exist?
- what failed?
- how was it evaluated?

It should also answer:

- which execution attempt am I looking at?
- did the agent ask for clarification?
- did a retry happen?
- which output belongs to which action or execution?

### Expected Sections

At minimum, a selected task should be able to show:

- task identity and status
- execution history or current execution
- ordered action history
- communication history
- outputs or resources
- error information if failed
- evaluation summary if present

Optional but important where relevant:

- stakeholder or communication trace
- timestamps
- action-level metadata

### Workspace Header

The workspace view should have a strong header area.

It should usually show:

- task name
- task status
- execution-at-a-glance state
- compact summary signals such as output count or latest update time

This gives the user orientation before they dive into dense evidence sections.

### Section Responsibilities

The sections should have distinct roles.

#### Overview

Shows:

- task identity
- current status
- parent or dependency context where useful
- currently active execution attempt if any

#### Executions

Shows:

- execution attempts in order
- start and end state
- retry boundaries
- high-level failure reason per attempt where relevant

#### Actions

Shows:

- ordered tool and worker actions
- start, completion, or failure state
- useful inputs and outputs
- action-level error details

#### Communication

Shows:

- agent messages
- stakeholder questions
- stakeholder answers

This section should read as a thread, not as a tool log.

#### Outputs

Shows:

- produced files
- resource names
- output availability
- download or inspect affordances where appropriate

Where outputs are versioned or updated over time, the workspace should make that legible rather than silently replacing old visible state.

#### Evaluation

Shows:

- task-level result
- criterion-level detail where useful
- enough judgment context to understand why the task passed or failed

## Graph View Versus Workspace View

The two surfaces should feel complementary rather than redundant.

### Graph View Should Feel

- spatial
- scannable
- low-density
- good for switching context

### Workspace View Should Feel

- focused
- information-dense
- chronological where needed
- suitable for debugging one task deeply

## Selection Rules

When a user clicks task A:

- task A becomes visibly selected in the graph
- task A detail renders in the detail pane

When the user clicks task B:

- task B becomes selected
- task B detail replaces task A detail

The detail pane must never show:

- stale task A detail while task B is selected
- mixed content from multiple tasks

If a new action or message arrives for task A while task B is selected:

- task B detail should remain visible
- task A's new activity should still be visible at the graph or summary level

## Topology Change Rules

If task status changes but topology stays the same:

- the node status should update
- the selected detail pane should remain bound to the same task

If topology changes structurally:

- the graph should rerender without corrupting existing task identity
- if the selected task still exists, selection should remain on it
- if the selected task no longer exists, the UI should reset selection explicitly

## Update Mapping For The Selected Task

When the selected task receives a live update, the UI should route it precisely.

### Execution Started, Completed, Failed, Or Retried

Update:

- overview
- executions section
- graph node status

### Action Started, Completed, Or Failed

Update:

- actions section
- overview counters if present
- graph node status only if task status changed

### Agent Or Stakeholder Message Arrived

Update:

- communication section

This should not be rendered as if it were a tool action.

### Output Or Resource Added

Update:

- outputs section
- evaluation section if new output affects visible judgment

### Evaluation Result Added

Update:

- evaluation section
- overview summary if useful

## Required Invariants

- selected node and detail pane are always synchronized
- execution history stays attributable to the correct task
- action history is ordered
- communication history is ordered
- outputs shown in the pane belong to the selected task
- evaluation shown in the pane belongs to the selected task
- failure shown in the pane belongs to the selected task
