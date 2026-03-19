# Cohort View

This document defines the `Experiment Cohort` view as the top-level FE operations surface.

The cohort view is where users monitor many runs at once and decide which run to inspect next.

## Purpose

The cohort view should help a user answer:

- what is this experiment cohort?
- how many runs are queued, running, completed, or failed?
- which runs need attention right now?
- which run should I click into next?

## Product Role

The cohort view is not just a list page.

It is the top-level operating surface for experiments at scale.

The intended product hierarchy is:

1. cohort
2. run
3. task
4. task workspace evidence

## Cohort Identity

A cohort should have a stable, explicit identity.

Example:

- `minif2f-react-worker-gpt-5-v3`

This identity should be supplied by the backend dispatch layer and treated as a real product concept, not as an ad hoc FE label.

## Header

The cohort header should show:

- cohort name
- launch or creation context if useful
- reproducibility metadata where available

Useful reproducibility metadata may include:

- code commit or snapshot id
- worker or prompt version
- model or provider version
- tool or sandbox config snapshot

The FE should be able to display this when the backend provides it.

## Summary Metrics

The cohort page should surface aggregate metrics that help with live operations.

Priority metrics:

- total runs
- counts grouped by status
- average score
- best score
- worst score
- duration summaries
- failure-rate summaries

These may require dedicated backend aggregation support.

## Mixed Benchmarks

Mixed-benchmark cohorts are valid.

That means the cohort page should not assume:

- one benchmark family per cohort

Instead, each run row should surface benchmark identity explicitly.

## Run List

The cohort should contain a large clickable list of runs.

Each run row should support fast scanning.

At minimum, the row should be able to show:

- run identity
- benchmark
- status
- running time so far or terminal duration

Useful secondary fields:

- score
- failure summary
- last updated time
- sample identity where available

## Primary Goal

The primary goal of the cohort page is:

- monitoring live progress across many runs

This means the view should optimize for:

- quick scanning
- status comprehension
- entry into the right run

not:

- deep per-task evidence

That belongs one level down.

## Interaction Model

### Click Into Run

Clicking a run should:

- open the run page
- preserve breadcrumb navigation back to the cohort

### Live Updates

The cohort should update as run states change.

At minimum it should react to:

- run status changes
- score arrivals
- duration updates
- failure summaries
- aggregate metric changes

## Visual Tone

The cohort view should feel:

- operational
- information-dense but clean
- suited for monitoring many runs at once

It should not feel like:

- a marketing dashboard
- an overloaded spreadsheet clone

## Anti-Patterns

Avoid:

- hiding benchmark identity in mixed cohorts
- showing misleading stale aggregate metrics without warning
- forcing the user to open each run to understand whether it needs attention
- overloading the cohort page with task-level evidence that belongs on the run page
