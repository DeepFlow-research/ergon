# Authoring API Redesign v2 Program Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:subagent-driven-development` or
> `superpowers:executing-plans` to implement this plan task-by-task. Steps
> use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the v2 redesign through small, runnable PRs with explicit
bridges and deletion gates.

**Architecture:** Add the new run-tier and object-bound paths beside the
old slug/definition paths, flip one vertical at a time, then delete the old
paths. The final architecture remains the accepted v2 spec from `01`-`08`.

**Tech Stack:** Python 3.11+, Pydantic v2, SQLModel, Alembic, Inngest,
pytest, SQLite unit tests, Postgres integration tests.

---

## Why This Program Exists

The old plan was still a big cut. It began by resetting schema and then
changed public API, persistence identity, runtime event shape, sandbox
lifecycle, builtins, and CLI semantics on the same long-running branch.
That makes failures ambiguous and makes review expensive.

This program is intentionally depth-first:

- add new data where old code can ignore it;
- add new typed boundaries beside old callers;
- flip one runtime path;
- prove one builtin vertical;
- migrate remaining callers;
- delete bridges.

## Destructive Step: Migration Reset In PR 11

**Before merging PR 11**, every machine with an Ergon dev DB must run
`alembic downgrade base` and tear down any persistent Docker volumes. PR 11
deletes the entire `ergon_core/migrations/versions/` directory and replaces
27+ revisions with one new `00000000_initial_v2.py` that has
`down_revision = None`. The workshop locked "no prod data" for v2 launch;
the same decision applies to contributors' local databases — there is no
data preservation path. See PR 11 § "Developer-facing downgrade step" for
the exact developer instructions and the CI invariant that locks the head
count to one.

## Churn Budget

| Area | Likely churn |
|---|---:|
| Core API + runtime + persistence | 6k-10k changed lines |
| Tests, fixtures, architecture guards | 3k-6k changed lines |
| Migrations / final schema reset | 1k+ changed lines |
| Builtins and CLI migration | 2k-4k changed lines |
| **Total PR chain** | **10k-18k changed lines** |

PRs above 2.5k non-generated changed lines must be split unless the excess
is mechanical deletion.

## Ownership Lanes

| Lane | Owns | Must not own |
|---|---|---|
| API | `ergon_core.api`, public exceptions, Pydantic round trips | Inngest orchestration |
| Persistence | ORM, Alembic, repositories, `RunGraphNodeView` | Worker/evaluator behavior |
| Runtime | jobs, Inngest registry, `worker_execute`, lifecycle ownership | Builtin benchmark factories |
| Sandbox | `api/sandbox`, `core/infrastructure/sandbox`, concrete builtins sandboxes | Definition/run identity |
| Builtins | benchmark constructors, workers, toolkits, one vertical at a time | Core migrations |
| CLI | `ergon_cli.commands.experiment`, slug factories, command tests | Public API design |
| Tests | architecture guards, regression net, walkthrough harness | Production implementation |

## Bridge Ledger

| Bridge | Introduced | New default | Deleted |
|---|---|---|---|
| Run-tier `task_json` beside definition payload | PR 1 | PR 3 | PR 11 removes old fields |
| `graph_repo.node(...).task` beside `_prepare_definition` | PR 2 | PR 3 | PR 11 |
| Synchronous-fanout criteria beside legacy `evaluate_task_run` body | PR 4 | PR 4 | PR 11 prunes legacy reads; `evaluate_task_run` survives reshaped |
| Object-bound `Task` beside `TaskSpec` | PR 5 | PR 6 for MiniF2F, PR 10 globally | PR 11 |
| Public `Experiment` beside domain `Experiment` | PR 5 | PR 8 | PR 11 |
| `Sandbox` subclasses beside `BaseSandboxManager` | PR 5/6 | PR 10 | PR 11 |
| Definition metadata beside `ExperimentRecord` | PR 7 | PR 7 | PR 11 |
| CLI slug factory beside `saved_specs` path | PR 8 | PR 8 | PR 11 |

## Ledger Files (executable program twin)

Four landing-PR-keyed `xfail(strict=True)` ledgers land in PR 0 / PR 1
alongside the existing transition ledger. Each later PR is responsible
for removing the markers for the invariants it lands; PR 11 asserts both
marker dicts are empty as a completion-bar guard. See
[`07-test-strategy.md` §0](../07-test-strategy.md) for the rationale and
the no-call-graph-mocks rule.

| File | Lands in | Marker store | Final-state owner |
|---|---|---|---|
| `test_v2_transition_ledger.py` | PR 0 | `TRANSITIONAL_SYMBOLS` | PR 11 replaces with deletion guards |
| `test_v2_final_state_ledger.py` | PR 0 | `_XFAIL_BY_NAME` | PR 11 empties the dict and adds completion-bar guard |
| `test_dead_path_audit.py` | PR 0 | `_XFAIL_BY_SYMBOL` | PR 11 empties the dict and adds completion-bar guard |
| `test_no_type_circumventors.py` | PR 0 | `_KNOWN_EXEMPTIONS` | PR 11 empties the dict and adds completion-bar guard |
| `test_repository_layer_conventions.py` | PR 0.5 | `_KNOWN_VIOLATORS` (file-shared) | PR 11 empties and removes the xfail on `test_no_repository_violators_remain` |
| `test_repository_companion_files.py` | PR 0.5 | `_KNOWN_VIOLATORS` (same dict, shared) | PR 11 empties (same) |
| `test_no_dead_repository_methods.py` | PR 0.5 | `_KNOWN_UNUSED_FOR_NOW` | PR 11 empties and removes the xfail on `test_no_dead_repository_methods_remain` |
| `test_walkthrough_smoketest.py` | PR 1 | per-test `@xfail` | PR 11 asserts no XFAIL remains |
| `test_identity_invariants.py` | PR 1 | per-test `@xfail` | PR 11 asserts no XFAIL remains |

Per-PR ledger updates (which markers each PR removes):

| PR | Final-state entries flipped | Dead-path entries flipped | Smoketest/identity flipped | Repo-standard entries flipped |
|---|---|---|---|---|
| 1 | — | — | — | `telemetry/repositories.py` rename (filename-singular case) |
| 2 | — | — | `test_task_id_propagates_into_runtime_task_instance` | — |
| 3 | `worker_execute_imports_only_run_tier` | `_prepare_definition` | `test_worker_execute_reads_task_from_run_tier_only` | — |
| 4 | `evaluate_task_run_uses_thin_payload`, `check_evaluators_is_unregistered` | — | 3 smoketest + 2 identity cases | `CreateTaskEvaluation` moves to `telemetry/models.py` |
| 5 | `task_has_no_model_post_init` | `_worker_from_payload_bridge`, `_DetachableSandboxBridge` | — | — |
| 7 | — | — | `test_persist_definition_writes_only_intended_tables` | `experiments/errors.py` added; ValueError raises replaced |
| 8 | — | `_persist_single_sample_workflow_definition` | — | — |
| 9 | `materialize_dynamic_subtask_definition_is_gone` | `materialize_dynamic_subtask_definition` | `test_dynamic_spawn_writes_only_to_run_graph_nodes`, `test_dynamic_task_id_has_no_definition_row` | — |
| 11 | all remaining entries | all remaining entries | `test_run_completion_releases_every_acquired_sandbox` | all remaining `_KNOWN_UNUSED_FOR_NOW` entries; remove xfail on `test_no_repository_violators_remain` and `test_no_dead_repository_methods_remain` |

PR 11 also runs the **Structural Simplification Audit** (10 named
candidates) — see [`12-pr-11-deletion-final-schema.md`](12-pr-11-deletion-final-schema.md)
§ Task 5. The audit produces a KEEP/RENAME/INLINE/SPLIT decision per
candidate in the PR description; it is a hand-checked review pass, not
a pytest assertion.

## PR Sequence

| PR | Name | Runnable after merge | Primary invariant |
|---:|---|---|---|
| 0 | Transition ledger | yes | Old paths are inventoried and guarded |
| 0.5 | Repository layer standard | yes | Repository conventions are documented and enforced; current violators xfailed |
| 1 | Run-tier task snapshot | yes | Run nodes can carry self-contained task JSON |
| 2 | Typed run-node boundary | yes | Repo can inflate typed tasks from run-tier JSON |
| 3 | Worker-execute typed node | yes | Worker execution prep uses run-tier typed node |
| 4 | Synchronous-fanout criteria | yes | Worker-execute orchestrates eval via `ctx.step.invoke` + gather; owns sandbox release in `finally` |
| 5 | Object-bound API | yes | New authoring objects serialize beside old adapters |
| 6 | MiniF2F vertical | yes | One builtin uses the v2 shape end to end |
| 7 | Persistence collapse | yes | New definitions launch without `ExperimentRecord` |
| 8 | CLI composition | yes | CLI define output is launchable by canonical launch |
| 9 | Dynamic subtasks | yes | Spawned tasks are graph-native |
| 10a | SWEBench vertical | yes | SWEBench uses object-bound `Task`/`Sandbox`; lands shared `ManagerBackedSandboxRuntime` adapter |
| 10b | ResearchRubrics vertical | yes | ResearchRubrics uses object-bound `Task`/`Sandbox`; `JudgeCriterion` becomes Pydantic |
| 10c | GDPEval vertical + builtins cleanup | yes | GDPEval uses object-bound `Task`/`Sandbox`; registry-import shrink + no-registry guard cover all four migrated benchmarks |
| 11 | Deletion + final schema | yes | Old paths are gone |
| 12 | Walkthrough + CI | yes | Canonical integration variants pass |

## PR 10 Sub-PR Sequencing

PRs 10a, 10b, 10c are **three independently-reviewable GitHub PRs**,
not a single PR with three internal tasks. Reviewers focus on one
benchmark at a time; the 2.5k-line churn budget applies per sub-PR.

| Sub-PR | Lands when | Depends on | Cross-cutting role |
|---|---|---|---|
| 10a — SWEBench | After PR 9 is on `main` | Lands the shared `ManagerBackedSandboxRuntime` adapter at `ergon_builtins/sandboxes/_manager_backed.py` | Adapter is imported by 10b/10c |
| 10b — ResearchRubrics | After PR 9; independent of 10a | Imports the adapter (if 10a already merged) — otherwise Step 0 instructs the author to create the adapter inline | Adds Pydantic `JudgeCriterion` |
| 10c — GDPEval + cleanup | **Must merge last** of the three | Imports the adapter; runs the no-registry guard across all four migrated benchmarks (minif2f, swebench_verified, researchrubrics, gdpeval) | Registry shrink + architecture guard |

The three sub-PRs do **not** depend on each other sequentially in
content — only the no-registry guard in 10c requires the other two to
be merged so its parametrized `_MIGRATED_BENCHMARKS` list passes for
every entry. If 10b lands before 10a, 10b's Step 0 lands the adapter;
if 10a lands first, 10b just imports it.

## PR Description Template

Every PR must include:

```markdown
### V2 Slice Ledger

Invariant landed:

Bridge code introduced:

Old path still intentionally alive:

Deletion gate:

Tests added or updated:

Modules owned by this PR:
```

## Parallelization Rules

Safe in parallel:

- PR 0 audit work and PR 1 schema exploration.
- PR 4 synchronous-fanout criteria draft after PR 2 defines `RunGraphNodeView`.
- PR 8 CLI draft after PR 5 defines public `Experiment`.
- PR 12 walkthrough draft after PR 6 proves one vertical path.

Do not parallelize changes to these files:

- `ergon_core/ergon_core/core/application/jobs/worker_execute.py`
- `ergon_core/ergon_core/core/application/experiments/definition_writer.py`
- `ergon_core/ergon_core/core/application/graph/repository.py`
- `ergon_core/ergon_core/core/persistence/telemetry/models.py`
- `ergon_cli/ergon_cli/commands/experiment.py`

## Final Deleted Symbols

PR 11 must remove all of:

**v1 public API and abstractions:**
- `ergon_core.api.registry.ComponentRegistry`
- `ergon_core.api.benchmark.task.TaskSpec`
- `ergon_core.core.domain.experiments.worker_spec.WorkerSpec`
- `ergon_core.core.domain.experiments.Experiment` (domain — public version in `ergon_core.api.experiment` replaces it)
- `Worker.from_buffer`
- `Worker.validate` (renamed to `validate_runtime_deps` in PR 5)

**Dead packages:**
- `ergon_core.core.persistence.saved_specs`
- `ergon_core.core.application.components` (ComponentCatalogService and friends)
- `ergon_core.core.application.experiments.repository.DefinitionRepository`

**Deprecated Inngest jobs (absorbed into worker_execute by PR 4):**
- `ergon_core.core.application.jobs.execute_task`
- `ergon_core.core.application.jobs.sandbox_setup`
- `ergon_core.core.application.jobs.persist_outputs`
- `ergon_core.core.application.jobs.check_evaluators`

**Runtime DTOs:**
- `EvaluateTaskRunRequest` (replaced by `TaskEvaluateRequest`, the id-only payload)
- `PreparedTaskExecution.node_id`, `.definition_task_id`, `.worker_type`, `.assigned_worker_slug`, `.model_target`
- `_prepare_legacy_definition`, `_worker_from_payload_bridge`, `_DetachableSandboxBridge`

**Schema (composite PK collapse):**
- `RunGraphNode.id` (composite PK becomes `(run_id, task_id)`)
- `RunGraphNode.definition_task_id`
- `RunGraphNode.parent_node_id` → renamed `parent_task_id`
- `RunGraphEdge.source_node_id` / `target_node_id` → renamed `source_task_id` / `target_task_id`
- `RunGraphEdge.definition_dependency_id`
- `RunTaskExecution.node_id` (renamed `task_id`), `.definition_task_id`
- `RunTaskEvaluation.node_id`, `.definition_task_id`
- `ergon_core.core.persistence.telemetry.models.ExperimentRecord` (table)

**Evaluation:**
- `CriterionExecutor`, `InngestCriterionExecutor`
- `terminate_sandbox_by_id`

**Kept and reshaped (PR 11 must NOT delete these):**

- `evaluate_task_run` Inngest function — survives as the per-evaluator
  fanout target. Body is rewritten in PR 4 to take the id-only
  `TaskEvaluateRequest`, reload state via `graph_repo.node`, attach the
  sandbox via `Sandbox.from_definition(sandbox_id=...)`, call
  `evaluator.evaluate(...)` directly (no `CriterionExecutor`), then
  detach. PR 11 only deletes the *v1 body and v1 payload class*, not
  the function/slug itself.

## Verification Commands

Run these at the end of every PR unless the PR-specific doc narrows the set:

```bash
uv run pytest ergon_core/tests/unit/architecture -q
uv run pytest ergon_core/tests/unit/api -q
uv run pytest ergon_core/tests/unit/runtime -q
```

PRs touching builtins also run:

```bash
uv run pytest ergon_builtins/tests/unit -q
```

PRs touching CLI also run:

```bash
uv run pytest ergon_cli/tests -q
```
