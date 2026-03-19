# Graph View Anatomy

This document defines the `Graph View` as a concrete product surface.

The graph view is not just a visualization.

It is the operator's structural map of the run.

## Purpose

The graph view should help a user answer:

- what tasks exist?
- how are they related?
- which tasks are pending, running, completed, failed, or blocked?
- where is the active frontier of work?
- where should I click next?

## Primary Role

The graph view is for:

- scanability
- topology comprehension
- failure localization
- task selection

It is not for:

- dense evidence inspection
- reading long logs
- reading chat threads
- deep evaluation analysis

That belongs in the workspace view.

## Layout Role

On the main run page, the graph view should usually occupy the left or central structural region.

It should be large enough to:

- show the visible DAG or tree clearly
- preserve orientation during live updates
- allow fast task switching

It should not be squeezed into a tiny minimap-sized panel.

## Graph Elements

### Nodes

Each node represents one task identity.

Every node should expose enough at-a-glance information to support scanning.

At minimum:

- task name
- task status
- selection state

Useful secondary signals:

- retry or execution-attempt marker
- output-present marker
- failure marker
- evaluation marker where relevant

The default node density should be:

- medium

That means:

- name
- status
- a small number of high-signal badges

It should not default to dense inline counters or long text inside nodes.

### Edges

Edges represent structural relationships.

At minimum they should communicate:

- dependency
- parent-child

depending on the real task model.

The important product property is:

- the user can understand the flow of work

### Regions And Clusters

If the graph becomes large, the UI may use clustering, grouping, or level sections.

But this must preserve:

- task identity
- relative topology
- the user's ability to trace failure paths

## Node Semantics

### Pending

Pending nodes should look inactive but available.

They should not look:

- failed
- hidden
- already completed

### Running

Running nodes should look active and time-sensitive.

The user should be able to scan the graph and immediately find active work.

### Completed

Completed nodes should look resolved and calm.

They should visually recede relative to running or failed nodes.

### Failed

Failed nodes should be immediately discoverable.

The graph should make failure concentration visually obvious.

### Blocked Or Waiting

If the system distinguishes blocked or waiting from pending, the graph should surface that difference clearly.

This matters because:

- "not started yet" and "cannot proceed" are different operator meanings

## Selection Model

The graph view is the primary task selector.

When a node is selected:

- the node must receive clear selection treatment
- the workspace view must switch to that task
- the selection should remain stable across rerenders

Selection styling must dominate over incidental status styling.

In other words:

- a running node must not look more selected than the selected node

## Live Update Behavior

The graph view must handle live updates safely.

### Task Status Change

When a task changes status:

- the node updates in place
- the node keeps its identity
- the selected node remains selected if it is still the same task

### New Task Added

When a new task appears:

- the graph should introduce it without making existing nodes appear to have changed identity
- the addition should be visually comprehensible

Subtle highlighting for new nodes or edges is appropriate.

The graph does not need to become its own event feed.

### New Edge Added

When an edge appears:

- the graph should preserve orientation
- the new relationship should be legible without forcing a full mental reset

### Selected Task Updated

When the selected task changes state:

- the node updates in place
- the workspace view updates in parallel

### Non-Selected Task Updated

When another task changes state:

- the graph updates that node
- the workspace view stays on the currently selected task

This is important.

The graph provides ambient situational awareness.

The workspace provides focused inspection.

Communication activity should not add graph noise by default.

For v1:

- no communication-specific signal is required on graph nodes

## Topology Changes

Topology changes are among the most dangerous UI moments because they can break identity.

The graph must explicitly support:

- node insertion
- edge insertion
- task removal or invalidation if the backend allows it
- re-layout without identity drift

Required invariant:

- if task `A` still exists after the update, task `A` should still be task `A`

## Recommended Visual Hierarchy

The graph should communicate, in descending order:

1. selection
2. failure and running activity
3. structural relationships
4. secondary metadata

This prevents noise from overwhelming the user's main questions.

## Interaction Rules

### Click

Clicking a node should:

- select the task
- move the workspace view to that task

### Hover

Hover can reveal lightweight summary information.

It should not be the only place important information lives.

### Keyboard Navigation

If keyboard support is added, it should preserve the same identity guarantees as mouse selection.

### Zoom And Pan

If graph size requires zoom and pan, those controls must not break selection comprehension.

## Empty And Partial States

If graph data is missing or partial:

- the UI should say so explicitly
- it should not silently render an empty canvas that looks like "no tasks exist"

Examples:

- graph is still loading
- graph is stale
- graph topology is unavailable but run metadata exists

## Anti-Patterns

Avoid:

- using the graph as the only place to inspect evidence
- overloading nodes with too much text
- allowing layout churn to destroy orientation
- letting live updates silently replace one task with another
- making selection ambiguous
- using graph nodes as miniature chat or log panels
