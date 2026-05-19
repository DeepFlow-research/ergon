# PR 11 Reconciliation Audit

Date: 2026-05-18

Branch audited: `codex/v2-pr-11-deletion-final-schema`

Worktree audited:
`/Users/charliemasters/.config/superpowers/worktrees/ergon/codex-v2-pr-11-deletion-final-schema`

GitHub PR: `https://github.com/DeepFlow-research/ergon/pull/65`

Head audited: `a6138755f3f1b4794b0c640c377c9e87dc42c6cf`

## Scope

This folder is a self-contained reconciliation audit of the PR 11 worktree at
the audited head above. It describes the code that currently exists on this
branch: the deletion work already present, the live runtime paths that remain
load-bearing, and the gaps that still keep PR 11 from being pure final-schema
cleanup.

The purpose here is narrower and sharper:

- Identify what dead code still remains on PR 11 head.
- Identify duplicated or split implementations that still make core hard to
  reason about.
- Separate completed PR 11 deletion/migration work from current PR 11 gaps.
- Propose how to keep the remaining PR 11 work mostly deletions, while naming
  the fixes that are now clearly not just mechanical deletion.

## Main Docs

- [dead_code.MD](dead_code.MD) lists dead, stale, and deletion-candidate code
  still present on PR 11 head.
- [duplication.mD](duplication.mD) explains each core construct/domain, the
  current implementation path, and the duplicate or competing logic still in
  tree.
- [pr11_gap_register.md](pr11_gap_register.md) prioritizes the gaps that make
  PR 11 not yet a clean final-schema deletion PR.
- [pr_stack_recut.md](pr_stack_recut.md) proposes how to edit or split the
  remaining PR work so PR 11 can become honest cleanup again.
- [post_pr16_flow_digest.md](post_pr16_flow_digest.md) summarizes the expected
  post-PR16 call paths for each audited core flow.

## Follow-On PR Plans

- [pr12-runtime-identity-and-dynamic-task-correctness.md](pr12-runtime-identity-and-dynamic-task-correctness.md)
  makes runtime task identity coherent and fixes dynamic child execution.
- [pr13-evaluation-cleanup.md](pr13-evaluation-cleanup.md) deletes the
  remaining evaluator v1 dispatch/fallback path.
- [pr14-public-api-registry-surface.md](pr14-public-api-registry-surface.md)
  deletes the core registry and persistent component catalog, and stabilizes
  the builtins toolkit surface.
- [pr15-dashboard-event-contracts.md](pr15-dashboard-event-contracts.md)
  aligns backend dashboard events with generated frontend contracts and live
  parsers.
- [pr16-core-debt-sweep.md](pr16-core-debt-sweep.md) performs the final dead
  code, stale comment, lifecycle duplication, xfail, and ledger cleanup sweep.

## Executive Summary

On PR 11 head, the runtime is largely object-bound in the happy path:
`Benchmark.build_instances()` returns `Task` objects, `persist_benchmark()`
stores full task snapshots, graph runtime reads inflate from
`run_graph_nodes.task_json`, `worker_execute` runs `task.worker`, and
`evaluate_task_run` selects `task.evaluators[index]`.

The remaining risk is no longer "we forgot to migrate everything." It is that
several final-state promises are only partially implemented:

- final schema identity collapse is incomplete;
- some code already assumes the final `RunGraphNode.task_id` model while the
  model still only has `id`;
- public registry/catalog surfaces are still exported and used;
- dynamic subtask tools still have both object-bound and slug/registry paths;
- dynamic child task workers can still receive `WorkerContext.task_id=None`,
  making the public context facade unreliable for recursive workers;
- worker-authored `spawn_task()` is not memoized as an Inngest step, while
  `plan_subtasks()` is, so replay can duplicate graph mutations;
- PR 11 commit `a613875` fixed the smoke parent/recursive-worker polling
  deadlock by moving smoke child waiting out of worker execution, so the
  follow-on runtime plan no longer needs to change smoke fixture wait
  semantics;
- sandbox lifecycle behavior is public-object-bound, but observability cleanup
  still assumes manager-owned lifecycle;
- evaluator binding fallback remains even though the receiver no longer
  supports it;
- live dashboard graph/context events now have PR 11 compatibility parsers for
  wrapped graph mutation events and backend context-part payloads, but generated
  event contracts and canonical frontend field names still need alignment;
- PR 11 smoke failures likely include concrete fixture/runtime issues, not only
  external flake.

Net: PR 11 can still become mostly deletion, but only after a short stack of
targeted cleanup/fix commits or micro-PRs lands on top of the current PR 11
branch.
