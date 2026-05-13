# 09 — Implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:subagent-driven-development` or
> `superpowers:executing-plans` to implement this program PR-by-PR. The
> detailed plan lives in the sibling folder
> [`09-implementation-plan/`](09-implementation-plan/).

**Goal:** Ship the v2 authoring/runtime redesign as a chain of runnable,
reviewable, depth-first PRs instead of one broad cut.

**Architecture:** The accepted v2 target from `01`-`08` is unchanged:
object-bound authoring, run-tier task snapshots, run-tier-only runtime
reads, synchronous-fanout criteria orchestrated by `worker_execute`, graph-native dynamic subtasks,
typed sandbox subclasses, and CLI composition over the Python API. The
implementation path uses temporary internal bridges so `main` stays
runnable after every PR.

**Tech Stack:** Python 3.11+, Pydantic v2, SQLModel, Alembic, Inngest,
pytest, SQLite unit tests, Postgres walkthrough integration.

---

## Program Docs

Read these in order:

| # | File | Owns |
|---|---|---|
| 00 | [`00-program.md`](09-implementation-plan/00-program.md) | Strategy, churn budget, ownership lanes, bridge ledger, PR sequence |
| 01 | [`01-pr-00-transition-ledger.md`](09-implementation-plan/01-pr-00-transition-ledger.md) | First guardrails: transition ledger and old-symbol inventory |
| 01b | [`01b-pr-0-5-repository-standard.md`](09-implementation-plan/01b-pr-0-5-repository-standard.md) | Repository layer standard and dead-method audit |
| 02 | [`02-pr-01-run-tier-task-snapshot.md`](09-implementation-plan/02-pr-01-run-tier-task-snapshot.md) | Additive run-tier `task_json` / `is_dynamic` foundation |
| 03 | [`03-pr-02-typed-run-node-boundary.md`](09-implementation-plan/03-pr-02-typed-run-node-boundary.md) | `from_definition` methods and `RunGraphNodeView` |
| 04 | [`04-pr-03-worker-execute-typed-node.md`](09-implementation-plan/04-pr-03-worker-execute-typed-node.md) | Flip worker execution prep to typed run nodes |
| 05 | [`05-pr-04-inline-criteria.md`](09-implementation-plan/05-pr-04-inline-criteria.md) | Synchronous-fanout criteria via `ctx.step.invoke` and sandbox release ownership (filename retained for stable links; content describes fanout, not inline) |
| 06 | [`06-pr-05-object-bound-api.md`](09-implementation-plan/06-pr-05-object-bound-api.md) | Public object-bound API plus definition-writer bridges |
| 07 | [`07-pr-06-minif2f-vertical.md`](09-implementation-plan/07-pr-06-minif2f-vertical.md) | First builtin vertical: MiniF2F object-bound path |
| 08 | [`08-pr-07-persistence-collapse.md`](09-implementation-plan/08-pr-07-persistence-collapse.md) | Collapse experiment metadata onto definitions behind bridges |
| 09 | [`09-pr-08-cli-composition.md`](09-implementation-plan/09-pr-08-cli-composition.md) | CLI define/run through `Experiment` and canonical launch |
| 10 | [`10-pr-09-dynamic-subtasks.md`](09-implementation-plan/10-pr-09-dynamic-subtasks.md) | Graph-native dynamic subtasks and containment facade |
| 11 | [`11-pr-10a-swebench.md`](09-implementation-plan/11-pr-10a-swebench.md) | PR 10a — SWEBench vertical (object-bound `Task`, `SWEBenchSandbox`, shared `ManagerBackedSandboxRuntime` adapter) |
| 11b | [`11b-pr-10b-researchrubrics.md`](09-implementation-plan/11b-pr-10b-researchrubrics.md) | PR 10b — ResearchRubrics vertical (Pydantic `JudgeCriterion`) |
| 11c | [`11c-pr-10c-gdpeval.md`](09-implementation-plan/11c-pr-10c-gdpeval.md) | PR 10c — GDPEval vertical + builtins cleanup (registry-import shrink and no-registry architecture guard) |
| 12 | [`12-pr-11-deletion-final-schema.md`](09-implementation-plan/12-pr-11-deletion-final-schema.md) | Delete bridges and regenerate final v2 schema |
| 13 | [`13-pr-12-walkthrough-ci.md`](09-implementation-plan/13-pr-12-walkthrough-ci.md) | Walkthrough integration and CI hardening |

## Executable Program Twin

The PR plan is mirrored by five `xfail(strict=True)` ledger files landed
in PR 0 / PR 1. Each subsequent PR removes its xfail markers; PR 11
asserts both marker dicts are empty as a hard completion-bar guard. See
[`07-test-strategy.md` §0](07-test-strategy.md) for the four-file ledger
pattern and the per-PR flip schedule in
[`09-implementation-plan/00-program.md` "Ledger Files"](09-implementation-plan/00-program.md).

## Completion Bar

The program is complete only when:

- `test_v2_final_state_ledger.py::_XFAIL_BY_NAME` is an empty dict.
- `test_dead_path_audit.py::_XFAIL_BY_SYMBOL` is an empty dict.
- Runtime reads no definition-tier task rows after prepare-run.
- `worker_execute` synchronously fans evaluators out via
  `ctx.step.invoke` to `evaluate_task_run`, gathers, then releases its
  sandbox in `finally`.
- `evaluate_task_run` takes the thin id-only payload
  `(run_id, task_id, execution_id, evaluator_index)` and rebuilds the
  live sandbox via `Sandbox.from_definition(json, sandbox_id=...)`.
- Dynamic subtasks write only to `run_graph_nodes`.
- In-tree builtins construct object-bound `Task` objects.
- CLI define/run delegates to canonical Python persistence and launch.
- `TaskSpec`, `WorkerSpec`, `ComponentRegistry`, `saved_specs`,
  `ExperimentRecord`, `definition_task_id`, `CriterionExecutor`,
  `InngestCriterionExecutor`, and `Worker.from_buffer` are gone.
  (`evaluate_task_run` and the eval-payload class are **kept and
  reshaped**, not deleted — see Δ.4 / Δ.5 in `08-decisions-log.md`.)
- Walkthrough integration passes happy path, failure cascade, dynamic
  spawn, and restart variants — including per-eval `step.invoke`
  observability through the synchronous fanout.

## What's Deferred

These remain out of scope for the v2 implementation program:

- Public `GraphMutator` / `GraphInspector` / `ResourceInspector` service
  classes.
- Synchronous `spawn_task(..., await_completion=True)`.
- Multiple agents per task or sandbox sharing.
- Cross-task data handoff via first-class `Task.inputs` / `Task.outputs`.
- `GraphSpawnGovernor` fork-bomb backpressure.
- `Task.instance_key` removal.
- Cohort runs from the CLI.

## On Acceptance

After PR 12 lands, graduate the accepted parts of this folder into
`docs/architecture/`, archive the active RFC folder, and update
`docs/architecture/01_public_api.md` plus
`docs/architecture/cross_cutting/sandbox_lifecycle.md` to point at the
shipped v2 surfaces.
