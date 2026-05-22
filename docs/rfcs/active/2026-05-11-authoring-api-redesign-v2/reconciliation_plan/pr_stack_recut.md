# PR Stack Recut Proposal

Date: 2026-05-18

Branch audited: `codex/v2-pr-11-deletion-final-schema`

## Goal

Keep PR 11 as close as possible to deletion/final-schema cleanup, while not
pretending that unresolved data-model and runtime gaps are mechanical deletion.

## Current State

PR 11 already contains a lot of valid deletion work: legacy bridge modules,
saved specs, executor modules, builtins registries, benchmark sandbox managers,
and old legacy workers are gone. The object-bound happy path is real.

The remaining work falls into three categories:

1. Mechanical deletion still appropriate for PR 11.
2. Small correctness fixes that can land on the PR 11 branch before final
   deletion.
3. Architectural decisions that need to be finished in the follow-on stack
   rather than hidden inside PR 11.

## Suggested Micro-PRs Or Commit Groups

### PR 11a: Smoke/runtime correctness patch

Purpose: get the current branch to a trustworthy baseline before schema churn.

Status on PR 11 head `a613875`: the smoke lifecycle portion of this patch has
landed. Smoke parent and recursive workers now plan children and return instead
of polling siblings inside `worker_execute`, dependency-free dynamic children
are readied on parent completion, dynamic worker payloads tolerate no model
target, object-bound `_type` rehydration strips discriminator fields before
Pydantic validation, and dashboard compatibility parsers cover wrapped graph
mutation/context-part payloads.

Include:

- Fix the GDPEval smoke worker registration mismatch.
- Restore or explicitly replace ResearchRubrics search/web tools if the
  benchmark contract requires them.
- Fix dynamic `WorkerContext.task_id` for dynamic children by passing the
  canonical graph id into the public facade, not only `node_id`.
- Make public `WorkerContext.spawn_task()` replay-safe under Inngest, matching
  the step-aware treatment already added for `plan_subtasks`.
- Preserve the landed smoke contract where parents plan children and return;
  move any remaining child-completion assertions outside parent worker polling.
- Delete or hard-error the evaluator binding fallback so it cannot invoke
  unsupported eval jobs.
- Remove duplicate failed-task sandbox termination from propagation if
  `sandbox_cleanup` is the owner.

This is a correctness patch, not final-schema deletion.

### PR 14: Registry deletion

Purpose: settle the mismatch between the PR 11 deletion list and live registry
usage by deleting the core process-local registry entirely.

Include:

- Replace workflow-service payload model lookup with task-json-derived payload
  handling.
- Replace dynamic subtask slug worker synthesis with object-bound Task creation
  only.
- Move smoke fixtures, CLI discovery, onboarding, REST startup, and test
  harnesses away from registry lookup.
- Remove public `registry` and `ComponentCatalog` exports.
- Delete persistent component catalog model/tests.
- Add architecture guards proving no source path imports `ergon_core.api.registry`.

### PR 11c: Schema identity decision and implementation

Purpose: resolve `node_id` vs `task_id` for real.

- Add final `RunGraphNode.task_id` composite identity, remove `id`, remove
  edge/telemetry bridge columns, update all repositories, read models, events,
  tests, and generated contracts.
- Remove `node_id` from `WorkerContext`, job payloads, task events, telemetry
  rows, dashboard registration, and test helpers.
- Regenerate final migration explicitly and verify generated frontend/backend
  contracts.
- Rename/replace `RunRecord.experiment_id` with `definition_id`.

### PR 11d: Definition metadata cleanup

Purpose: decide how much normalized definition metadata remains beside
`task_json`.

Include:

- Decide whether `ExperimentDefinitionWorker`, `ExperimentDefinitionEvaluator`,
  task assignment, task evaluator, and `task_payload_json` remain final schema
  or are bridge-only.
- Retain normalized evaluator metadata rows for evaluator FK/read-model/query
  ergonomics.
- Do not remove evaluator rows in the cleanup stack unless a later dedicated
  schema PR replaces the evaluation persistence FK strategy.
- Fix launch provenance between `ExperimentDefinition`, `BenchmarkDefinitionRecord`,
  and the new `RunRecord.definition_id`.

### PR 11e: Mechanical deletion and ledgers

Purpose: the actual PR 11 deletion pass after the above is settled.

Include:

- Delete dead evaluator dispatch DTOs/service/tests.
- Delete `Task.evaluator_binding_keys`.
- Delete `minif2f/_legacy_toolkit.py`.
- Delete `output_extraction.py` if no external import contract remains.
- Delete persistent component catalog if the registry decision says it is dead.
- Remove stale docs/comments.
- Drain remaining architecture ledgers and un-xfail walkthrough completion
  guard. No known-violator ledgers or xfails remain.

### PR 12a or PR 11f: Dashboard contract alignment

Purpose: prevent schema/identity cleanup from leaving the live dashboard on
stale event shapes.

Include:

- Generate graph/context dashboard events as first-class frontend contracts, or
  update handwritten live parsers to match backend payloads exactly.
- Replace frontend `source_node_id` / `target_node_id` graph vocabulary with
  `source_task_id` / `target_task_id` if PR 11 keeps that final naming.
- Align `workflow.started` task-tree fields with backend generated schemas.
- Update TS test-harness DTOs from `parent_node_id` to `parent_task_id`.

## Recommendation

Do not merge PR 11 as-is. It is not just missing a few final deletes; it has a
mixed schema identity state and live registry mismatch. The fastest honest path
is probably:

1. land a small smoke/runtime correctness commit group on the PR 11 branch;
2. delete the core registry and persistent component catalog;
3. choose and implement one runtime identity model;
4. then perform the remaining deletion/ledger cleanup.

That still preserves the spirit of PR 11: it becomes the branch where old paths
die. It just stops asking the deletion PR to also quietly invent unresolved
architecture.
