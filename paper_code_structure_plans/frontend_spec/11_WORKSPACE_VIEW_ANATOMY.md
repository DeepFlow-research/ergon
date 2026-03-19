# Workspace View Anatomy

This document defines the `Workspace View` as a concrete product surface.

The workspace view is where the user inspects one selected task deeply.

It should feel like a debugging workspace, not like a thin inspector.

## Purpose

The workspace view should help a user answer:

- what is this task doing now?
- what happened in this task?
- which execution attempt am I looking at?
- what tools ran?
- what messages were exchanged?
- what outputs exist?
- how was the task evaluated?

## Primary Role

The workspace view is for:

- evidence inspection
- chronology
- communication review
- output inspection
- evaluation interpretation

It is not for:

- understanding the full run topology at a glance
- locating failure across the whole run

That belongs in the graph view.

## Layout Role

On the main run page, the workspace view should usually occupy the right or main evidence region.

It should be large enough to support:

- scrolling through action history
- reading communication
- inspecting outputs
- reading evaluation detail

The workspace should not feel cramped or modal by default.

## Workspace Structure

The workspace view should have a stable internal structure.

At minimum:

- workspace header
- primary evidence area
- secondary sections or tabs

## Workspace Header

The header should orient the user immediately.

It should usually show:

- task name
- task status
- current execution attempt or retry signal
- latest meaningful update time if available

Useful secondary signals:

- output count
- evaluation summary
- failure badge

The user should always be able to answer:

- which task am I looking at?

without scrolling.

## Primary Evidence Area

The workspace should have one visually primary area.

Depending on the task, this may be:

- output preview
- action timeline
- communication thread
- failure summary

The exact dominant pane can vary by task type, but the user should never need to hunt across six equal-weight boxes to find the main evidence.

Default rule:

- outputs and artifacts are the primary pane when they exist

## Secondary Sections

The workspace should expose distinct sections for different evidence types.

At minimum:

- overview
- executions
- actions
- communication
- outputs
- evaluation

These may be tabs, stacked sections, or a hybrid.

The important product rule is:

- each evidence type has a predictable home

## Section Semantics

### Overview

Shows:

- task identity
- current state
- compact task summary
- current execution context

This section is for orientation, not dense chronology.

### Executions

Shows:

- execution attempts in order
- start, completion, or failure state per attempt
- retry boundaries
- high-level reason for retry or failure where available

The point is to make retries legible rather than flattening them away.

### Actions

Shows:

- ordered tool or worker actions
- start, completion, or failure state
- useful timing
- useful inputs and outputs
- action-specific errors

This should read like a timeline.

The user should be able to understand:

- what happened first
- what happened next
- where failure occurred

### Communication

Shows:

- agent messages
- stakeholder questions
- stakeholder answers
- other materially relevant communication items

This should read like a conversation thread.

It must be visually distinct from the actions section.

The user should never confuse:

- a tool invocation
- a human or agent exchange

### Outputs

Shows:

- produced files
- artifacts
- output availability state
- versioning or replacement history where relevant

If outputs are central to the task, this section may deserve primary visual emphasis.

### Evaluation

Shows:

- task-level verdict
- score if applicable
- criterion-level detail where useful
- explanation of why the task passed or failed

This section should read like judgment, not like a raw event log.

## Live Update Behavior

The workspace must update precisely when the selected task changes.

### Execution Update

Should update:

- header
- executions section
- overview

### Action Update

Should update:

- actions section
- summary counts if present

### Communication Update

Should update:

- communication section

### Output Update

Should update:

- outputs section
- any primary output preview if present

## Dynamic Fallback Rules

If the selected task has no outputs yet, the workspace should not leave the primary pane empty by default.

Preferred fallback behavior:

- if the task is running, foreground the action timeline
- if the task failed before producing outputs, foreground a failure summary plus the most relevant recent actions
- if the task is waiting on communication, foreground the communication section
- if the task is queued or otherwise quiet, foreground the execution or task overview

### Evaluation Update

Should update:

- evaluation section
- header summary if helpful

## Non-Selected Task Behavior

If another task changes while this workspace is open:

- the current workspace should stay bound to the selected task
- the graph view should reflect the other task's change

The workspace should not jump unexpectedly.

## Chronology Rules

The workspace should preserve chronological clarity.

Required properties:

- execution attempts remain in order
- action history remains in order
- communication remains in order
- new items append or merge in a way that preserves meaning

## Failure Behavior

When the selected task fails, the workspace should make failure actionable.

The user should be able to see:

- terminal failure state
- the execution attempt that failed
- the last relevant actions
- relevant communication
- missing or incomplete outputs
- evaluation consequences where relevant

## Partial State Behavior

The workspace must handle partial truth clearly.

Examples:

- execution started but no actions completed yet
- actions exist but outputs do not
- outputs exist but evaluation has not arrived
- communication exists but no output was produced

These states should look incomplete, not broken.

## Suggested Visual Density

The workspace should be denser than the graph view.

That means it can support:

- richer text
- timelines
- message threads
- artifact cards
- judgment blocks

But density should still be structured.

The workspace should not become an undifferentiated wall of logs.

## Anti-Patterns

Avoid:

- mixing chat messages into the tool-action list
- flattening retries into one opaque status
- burying outputs behind too many clicks
- making evaluation impossible to relate back to evidence
- allowing the workspace to silently switch tasks
- keeping an empty outputs pane in primary position when another evidence surface is more meaningful
