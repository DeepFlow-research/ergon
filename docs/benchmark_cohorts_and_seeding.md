# Benchmark Cohorts And Seeding

This document explains the current local operator workflow for benchmark preparation, benchmark seeding, and cohort-backed execution.

The important model split is now:

- `Experiment` = a persisted benchmark task definition
- `Run` = one real execution attempt of an `Experiment`
- `ExperimentCohort` = a named grouping of many `Run`s for monitoring and comparison

## Core Rule

Seeding does not create runs.

That means:

- `magym benchmark seed ...` creates `Experiment` rows and any required input resources
- it does not create `Run` rows
- it therefore does not create cohort membership by itself

This is intentional.

The frontend cohort pages should reflect real executions, not preload artifacts created during dataset setup.

## What The Tables Mean

### `experiments`

An `Experiment` stores the benchmark task definition and any persisted task-tree/resource information needed to execute it later.

The same `Experiment` may be executed many times over time.

### `runs`

A `Run` stores one actual execution attempt against an `Experiment`.

A run is where the system records:

- execution status
- timing
- outputs
- scores
- errors
- execution metadata

So a `Run` should only exist when something is actually being executed.

### `experiment_cohorts`

An `ExperimentCohort` is the operator-facing grouping used to monitor a named batch of runs.

Examples:

- `minif2f-react-gpt5-v3`
- `researchrubrics-baseline-ablation-a`
- `smoke-demo-2026-03-19`

Each new run should belong to exactly one cohort on the main execution path.

## Current Command Semantics

### Prepare benchmark assets

```bash
magym benchmark prepare minif2f researchrubrics
```

This prepares benchmark-specific assets locally.

### Seed benchmark definitions

```bash
magym benchmark seed minif2f researchrubrics --database main --limit 10
```

This creates benchmark definitions in Postgres.

Today that means:

- create `Experiment` rows
- create input `ResourceRecord` rows
- create no `Run` rows
- create no cohort rows

If you are preparing backend or frontend fixtures from static benchmark definitions, this is the right command.

### Run a cohort-backed execution

Use the unified top-level `magym` run command:

```bash
magym benchmark run smoke_test --workflow single --cohort-name smoke-demo
```

That path:

- emits a `BenchmarkRunRequest`
- resolves or creates the named cohort
- persists a real `Run` with `cohort_id`
- starts workflow execution

You can also run all workflows for a runnable benchmark:

```bash
magym benchmark run smoke_test --all --cohort-name smoke-suite
```

`magym benchmark run` now has two launch backends:

- workflow-factory launch for `smoke_test`
- seeded-experiment launch for `minif2f` and `researchrubrics`

### Workflow-factory run path

Use this when the benchmark exposes named workflow factories:

```bash
magym benchmark run smoke_test --workflow single --cohort-name smoke-demo
```

This path rebuilds the workflow server-side, persists a new `Experiment` and `Run`, and then starts execution.

### Seeded-experiment run path

Use this when the benchmark is dataset-driven and should execute previously seeded definitions:

```bash
magym benchmark run minif2f --task-id amc12a_2008_p25 --cohort-name minif2f-demo
magym benchmark run minif2f --limit 5 --cohort-name minif2f-batch
magym benchmark run researchrubrics --experiment-id 11111111-1111-1111-1111-111111111111 --cohort-name rr-demo
```

This path:

- selects existing seeded `Experiment` rows
- resolves or creates the named cohort
- persists fresh `Run` rows against those experiments
- starts execution from the stored `Experiment.task_tree`

Exactly one selector is required for seeded-experiment benchmarks:

- `--experiment-id`
- `--task-id`
- `--limit`

The current runnable benchmark set is:

- `smoke_test`
- `minif2f`
- `researchrubrics`

## How To Think About FE Fixtures

Use two different setup paths depending on what the frontend test needs.

### If the FE test needs static benchmark definitions

Use:

```bash
magym benchmark seed ...
```

This is suitable for:

- definition-level fixture setup
- seeded experiment lists
- backend fixture creation where no execution has happened yet

### If the FE test needs live cohort/run state

Use:

```bash
magym benchmark run smoke_test --workflow single --cohort-name fe-demo
magym benchmark run minif2f --limit 3 --cohort-name fe-minif2f
```

This is suitable for:

- cohort list/detail views
- run pages reached from cohort context
- live updates and cohort summary metrics
- breadcrumb navigation from run page back to cohort

## Recommended Workflow Before FE Tests

1. Prepare benchmark assets with `magym benchmark prepare ...`
2. Seed reusable benchmark definitions with `magym benchmark seed ...`
3. Start real executions with `magym benchmark run ... --cohort-name ...`
4. Point FE tests at those real `Run` and `ExperimentCohort` records

## Short Summary

Use `seed` to create reusable benchmark definitions.

Use `magym benchmark run ... --cohort-name ...` to create real runs:

- with `--workflow` or `--all` for `smoke_test`
- with `--experiment-id`, `--task-id`, or `--limit` for `minif2f` and `researchrubrics`

Do not assume that seeding creates runs or cohorts anymore.
