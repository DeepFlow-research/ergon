# Product Overview

## Purpose

The Arcane frontend is the operator and debugging surface for experiment cohorts and benchmark runs.

Its primary job is not to generate truth.

Its job is to make backend truth inspectable, understandable, and debuggable.

## Core Product Question

When a cohort or run is executing or has finished, can a user quickly answer:

- what is happening across the experiment?
- what is happening?
- what happened?
- what failed?
- what evidence supports that?

If the UI cannot answer those questions, it is failing its core purpose.

## Primary User Outcomes

The frontend must let a user:

- monitor many runs inside an experiment cohort
- see aggregate live progress across a cohort
- see all relevant runs
- identify which runs are pending, running, completed, or failed
- open a run and understand its task graph
- inspect one task at a time in detail
- see actions, outputs, errors, and evaluation for that task
- watch state change live without constant refreshes
- understand failure from visible evidence instead of guesswork
- zoom from cohort -> run -> task without losing context

## Non-Goals

The frontend is not responsible for proving backend correctness.

That belongs to:

- deterministic state tests
- contract tests
- sandbox lifecycle tests

The frontend should assume the backend truth model exists and render it faithfully.

## Product Principles

### 1. Debuggability Over Decoration

The UI should prioritize:

- clear state
- clear evidence
- clear transitions

over:

- ornamental complexity
- visually impressive but ambiguous widgets

### 2. Graph Plus Evidence

The frontend must provide both:

- structural context via the run graph
- detailed evidence via the selected run or task view

The graph alone is not enough.

The detail pane alone is not enough.

At the product level, the frontend must also provide:

- cohort-level operational context

The system is not just a single-run debugger.

### 3. Stable Identity

The UI must preserve identity correctly across:

- task selection
- state changes
- graph updates
- live event application

A pretty graph that binds the wrong detail pane is a product bug.

### 4. Live State Must Feel Trustworthy

Users should not need to wonder whether:

- the page is stale
- the graph is behind
- a task is still selected correctly
- a completed badge is premature
- a cohort summary is hiding lagging or failed runs

### 5. Failures Must Be Actionable

A failed run should show:

- what failed
- where it failed
- the last relevant evidence
- enough surrounding context to decide the next step

Not just:

- a red badge
- a vague generic message

## Success Criteria

The frontend is succeeding when a user can:

- monitor cohort progress across many runs confidently
- drill from a cohort into the right run quickly
- inspect a completed run quickly
- diagnose a failed run quickly
- track a running run confidently
- trust that visible state corresponds to backend reality
