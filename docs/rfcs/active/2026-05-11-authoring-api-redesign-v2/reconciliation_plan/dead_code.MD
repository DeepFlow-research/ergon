# Dead Code Audit On PR 11 Head

Date: 2026-05-18

Branch audited: `codex/v2-pr-11-deletion-final-schema`

## Confirmed Deleted On PR 11 Head

The following legacy packages, bridge modules, and registry files are absent
from PR 11 head and should be treated as completed deletion work, not remaining
dead code:

- `ergon_core.core.persistence.saved_specs`
- `ergon_core.core.application.jobs._legacy_worker_bridge`
- `ergon_core.core.application.jobs._legacy_evaluator_bridge`
- `ergon_core.core.application.jobs.check_evaluators`
- `ergon_core.core.application.evaluation.executors`
- `ergon_core.core.application.evaluation.inngest_executor`
- per-benchmark `_legacy_workers.py` files
- per-benchmark `sandbox_manager.py` files
- `ergon_builtins.registry`, `registry_core`, `registry_data`

PR 11 has already done meaningful bridge deletion. The rest of this file lists
code that is still present on the audited branch.

## Strong Dead-Code Candidates

### Evaluator v1 dispatch DTO path

`EvaluationService.prepare_dispatch()` in
`ergon_core/ergon_core/core/application/evaluation/service.py` reconstructs
evaluator dispatches from definition tables, but the production path now fans
out from `execute_task._fan_out_evaluators()` into `TaskEvaluateRequest`. The
remaining references are tests and stale comments. The related internal models
in `ergon_core/ergon_core/core/application/evaluation/models.py` are also
candidate deletions:

- `PreparedEvaluation`
- `EvaluationDispatch`
- internal `TaskEvaluationContext`
- internal `CriterionContext`

Keep only if a non-runtime planning API explicitly needs them; otherwise delete
with the v1 dispatch tests.

### Evaluator binding fallback

`Task.evaluator_binding_keys` still exists in
`ergon_core/ergon_core/api/benchmark/task.py`, and
`execute_task._fan_out_evaluators()` still falls back to it when
`task.evaluators` is empty. On PR 11, `persist_benchmark()` rejects
`evaluator_binding_keys`, and `evaluate_task_run` only indexes
`task.evaluators`. If the fallback fires, it sends evaluator jobs that the
receiver rejects.

This should be deleted rather than retained as a bridge.

### MiniF2F legacy toolkit

`ergon_builtins/ergon_builtins/benchmarks/minif2f/_legacy_toolkit.py` appears
unreferenced by source search and duplicates active MiniF2F tool logic in
`ergon_builtins/ergon_builtins/benchmarks/minif2f/_tools.py`. It also contains
comments pointing at deleted `_legacy_workers.py` files.

### Context-output extraction

`ergon_core/ergon_core/core/application/context/output_extraction.py` rebuilds
`WorkerOutput` from context events. The live output path is now terminal stream
item to `WorkerOutputRepository.persist()` to `RunTaskExecution.worker_output_json`.
This file is marked with a TODO saying much of it may be dead after PR 11.

### Run cleanup sandbox teardown

`run_cleanup` is still registered/emitted, but its sandbox teardown path reads
`RunRecord.summary_json["sandbox_id"]`. The active per-task sandbox id is now
stamped on `RunTaskExecution`. Unless a run-level sandbox id is intentionally
reintroduced, this cleanup branch is stale.

### WorkflowService lifecycle duplicates

`WorkflowService.restart_task()` and `WorkflowService.abandon_task()` duplicate
task lifecycle operations with weaker behavior than `TaskManagementService`.
The workflow-service path directly changes status and does not apply the
terminal guards, cascade invalidation, dispatch, or containment behavior owned
by the task-management path. CLI non-dry-run paths reject these actions, so the
remaining active surface appears mostly test/legacy.

### Persistent component catalog model

`ergon_core/ergon_core/core/persistence/components/models.py` still defines the
old persistent component catalog table model. The source audit found no
production source references except the model/tests. PR 14 deletes this model
and its tests alongside the core registry deletion.

### Stale completion/test artifacts

`ergon_core/tests/unit/runtime/test_walkthrough_smoketest.py` still has an
xfailed completion-bar test for sandbox acquire/release. The PR 11 plan says
this should be un-xfailed and enforced.

`ergon_core/tests/unit/architecture/test_repository_companion_files.py` still
has one `_KNOWN_VIOLATORS` entry, despite the PR 11 plan requiring ledger
completion.

The PR 11 plan references `scripts/single_use_helper_audit.py`, but `rg --files
scripts` did not find it.

## Stale Docs And Comments

These are not runtime dead code, but they will confuse the next person reading
the branch:

- `ergon_builtins/AGENTS.md` still documents deleted `registry_core.py` as the
  source of truth.
- `ergon_builtins/ergon_builtins/benchmarks/minif2f/workers.py` and
  `swebench_verified/workers.py` still mention deleted legacy bridge files.
- `ergon_builtins/ergon_builtins/benchmarks/researchrubrics/_tools.py` says Exa
  tools remain on legacy worker classes, but those classes/files are gone.
- `ergon_builtins/ergon_builtins/evaluators/criteria/code_check.py` still refers
  to deleted Inngest criterion executor wiring.
- `ergon_core/ergon_core/core/application/evaluation/service.py` still mentions
  `evaluate_legacy` even though the method is gone.
- TS test harness helpers still expose deleted `parent_node_id` while the
  backend harness returns `parent_task_id`.

## Live Runtime Code That Should Not Be Deleted Blindly

`execute_task.py`, `sandbox_setup.py`, `worker_execute.py`,
`persist_outputs.py`, `evaluate_task_run.py`, and `sandbox_cleanup.py` are live
runtime pieces on PR 11 head. They should be simplified around the final
architecture, but they are not deletion targets as a group.

`ExperimentDefinition*` rows are duplicated with object-bound `task_json`, but
they are still load-bearing for definition persistence, evaluator FK lookup,
task assignment, run initialization, and read models. They are not safe to
delete as "dead code" without a schema redesign.
