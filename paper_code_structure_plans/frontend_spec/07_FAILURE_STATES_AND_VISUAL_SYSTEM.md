# Failure States And Visual System

## Visual System Goal

The frontend should communicate meaning clearly before it communicates polish.

The intended tone is:

- dense research and debugging cockpit

not:

- consumer-product minimalism
- decorative dashboarding

Styling should reinforce:

- status
- hierarchy
- selection
- failure severity
- evidence visibility

It should also reinforce the difference between:

- graph view
- workspace view

These two surfaces should feel related, but not visually identical.

## Graph View Versus Workspace View Styling

The graph view and workspace view should have different visual densities.

### Graph View

Should feel:

- spatial
- calm enough to scan quickly
- status-forward
- selection-aware

This is the place for:

- node state
- dependency lines
- structural emphasis

Not for dense evidence text.

### Workspace View

Should feel:

- grounded
- information-dense
- chronologically readable
- obviously task-scoped

This is the place for:

- execution history
- action timeline
- communication thread
- outputs
- evaluation

The workspace should read more like a debugging desk than a floating tooltip.

## Status Styling Semantics

The UI should make these states clearly distinguishable:

- pending
- running
- completed
- failed

This distinction should not rely on color alone.

The overall layout should be:

- information-dense but clean

not:

- sparse for its own sake
- visually noisy in a way that obscures meaning

Use:

- label text
- iconography
- emphasis
- layout hierarchy

in addition to color.

The same principle applies to update categories.

Users should be able to tell apart:

- execution state
- tool activity
- communication activity
- output availability
- evaluation result

without reading raw JSON or decoding subtle styling accidents.

## Visual Language By Update Type

Different update types should look different.

### Task Topology Changes

Use styling that communicates structural change rather than success or failure.

Examples:

- new node introduction highlight
- subtle edge reveal
- temporary "new" emphasis if helpful

### Execution Updates

Use styling that communicates attempt lifecycle.

Examples:

- running spinner or pulse
- completed resolved state
- failed high-contrast error state
- retry marker or attempt badge

Running-state animation should be:

- moderate

Users should be able to spot active work quickly without turning large cohorts into a sea of distracting motion.

### Action Updates

Render as an ordered timeline or log-like list with strong chronological readability.

Each action row should make clear:

- action name
- current state
- start or end time if available
- failure versus success

### Communication Updates

Render as a conversation-style thread or message stream distinct from actions.

It should be obvious that a stakeholder answer is not a tool invocation.

The styling difference should be strong enough that the user can visually switch between:

- "what the system did"
- "what the agent or stakeholder said"

### Output Updates

Render as artifact cards, rows, or chips with clear availability state.

The user should be able to tell:

- output exists
- output is missing
- output is expected but not yet available

Where useful, outputs can be treated as the central pane of the workspace, with surrounding sections providing provenance and judgment.

### Evaluation Updates

Render as judgment-oriented UI, not as a raw event log.

The user should be able to tell:

- evaluation exists
- evaluation passed or failed
- score or verdict at the right scope

## Failure States

### Failed Task

The user should see:

- clear failed status
- clear failure reason
- the last useful evidence
- no misleading completion affordances

Failure styling should be:

- clearly prominent

But it should stop short of making the whole interface feel like alarm fatigue.

If failure followed one or more actions or retries, the UI should preserve that buildup rather than collapsing to a single terminal badge.

### Failed Run

The user should see:

- clear run-level failure state
- enough summary to know where to inspect next
- a visible path to the failed task

If multiple tasks failed or became blocked, the graph should make the concentration of failure visually legible.

## Loading States

The UI should use loading states only when data is actually unresolved.

Loading UI should not:

- masquerade as empty state
- masquerade as success
- persist after terminal truth is known

## Empty States

The UI should define explicit empty-state behavior for:

- no runs yet
- no actions yet for a task
- no outputs yet
- no evaluation yet

Empty state should mean:

- nothing exists yet

not:

- something broke silently

## Partial State

Partial state must render clearly.

Examples:

- task exists, but outputs are not present
- run exists, but evaluation has not arrived
- graph exists, but no task is selected yet
- communication thread exists, but no outputs exist yet
- execution attempt exists, but no completed actions exist yet

The UI should make this understandable without implying contradiction.

The preferred philosophy is:

- show only meaningful missing sections

Do not fill the whole page with placeholders when a quieter omission communicates the state more cleanly.

## Selection Styling

Selected graph node and selected detail pane should have a clear visual relationship.

Users should not need to wonder:

- which task am I looking at?

The selected-task styling should dominate over incidental activity styling.

In other words:

- a running unselected node should not look more selected than the actually selected node

## Layout Expectations

The visual hierarchy should make it easy to scan:

1. run state
2. graph context
3. task evidence

Do not bury the main evidence behind excessive modal depth or secondary navigation.

The ideal reading pattern is:

1. scan the graph view
2. lock onto one task
3. inspect that task inside the workspace view

## Staleness And Connection Semantics

If live updates are delayed, disconnected, or stale, the UI should say so explicitly.

This should usually appear at run scope rather than inside every section.

The user should be able to distinguish:

- "nothing new has happened"
- "the view may be stale"

This distinction should be explicit and noticeable.

Silent staleness is one of the most dangerous FE failure modes in this product.

## Raw Events Drawer Styling

The raw events drawer should feel:

- operator-facing
- secondary
- high-density

It should default to:

- a filtered event stream that is readable under pressure

while still supporting:

- a rawer chronological mode for deeper debugging
