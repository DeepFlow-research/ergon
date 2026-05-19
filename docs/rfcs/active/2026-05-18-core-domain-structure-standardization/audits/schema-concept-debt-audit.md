# Schema Concept Debt Audit

Date: 2026-05-18

Audited against PR 16 head in the main checkout.

## Purpose

This audit looks above the level of "which package owns persistence?" and asks
whether the schema still carries concepts that no longer match v2:

- old tables that are no longer populated by the canonical path;
- tables that are active only for dashboard/test-harness compatibility;
- duplicated identity columns;
- fields that encode pre-object-bound worker/evaluator/sandbox selection;
- invalid or suspicious foreign keys;
- product concepts that have been deprecated in Python but still shape the
  database and frontend contracts.

## Classification

### Keep

Concept is active and aligned with v2.

### Keep, But Rename Or Document

Concept is active but the name reflects older vocabulary.

### Compatibility Only

Concept is still read or written, but only for dashboard, CLI, RL, test harness,
or transitional compatibility. It should not be used by new core runtime code.

### Suspect

Concept appears stale, invalid, or under-used. It needs a focused verification
before deletion.

### Delete Candidate

No active production writer/reader was found, or the concept directly
duplicates a canonical v2 path.

## Table Families

### Definition Tables: Keep

```text
experiment_definitions
experiment_definition_workers
experiment_definition_evaluators
experiment_definition_instances
experiment_definition_tasks
experiment_definition_task_dependencies
experiment_definition_task_assignments
experiment_definition_task_evaluators
```

These remain the immutable authored definition tier. The canonical v2 authoring
path writes them through `application/experiments/definition_writer.py`, and
runtime preparation copies them into run-tier graph rows.

Debt:

- The Python/table vocabulary still says `experiment_definition`, while the
  architecture now mostly says `definition`. This is naming debt, not dead
  schema.
- `experiment_definition_tasks.task_payload` and
  `experiment_definition_tasks.task_json` duplicate authored task state. The
  full object-bound `task_json` is canonical for runtime reconstruction, while
  `task_payload` remains as payload-specific compatibility/read convenience.
  New code should not treat `task_payload` as an alternate authoring source.
- Worker assignment and task-evaluator join rows duplicate information that is
  also inside object-bound `task_json`. Some duplication is still load-bearing:
  worker definition rows feed execution metadata and evaluator rows feed
  `RunTaskEvaluation.definition_evaluator_id`. The final target should be
  documented: either keep normalized rows as read/index/provenance tables, or
  simplify once no runtime path needs them.

Recommended action:

- Keep all definition tables for now.
- Mark `task_payload` as compatibility/derived from `task_json`.
- Decide whether normalized worker/evaluator assignment tables are permanent
  provenance/index tables or cleanup targets.

### Run Graph Tables: Keep

```text
run_graph_nodes
run_graph_edges
run_graph_annotations
run_graph_mutations
```

These are the v2 run-tier runtime graph. `run_graph_nodes.task_id` is now the
canonical runtime task identity, and `run_graph_nodes.task_json` is the runtime
task snapshot used by `WorkflowGraphRepository.node()`.

Debt:

- Some application/CLI/test code still says `node_id` when it means `task_id`.
  The schema mostly completed the identity collapse, but naming debt remains in
  method parameters, DTOs, tests, and comments.
- The schema comments in `RunGraphNode.status` say graph status is free-form
  and experiment-owned, while `persistence/graph/status_conventions.py` now
  provides core runtime status literals. That is conceptual drift: status
  semantics have become core runtime vocabulary.
- `RunGraphAnnotation` and `RunGraphMutation` are valid storage concepts, but
  they should be kept read-only/append-only from application graph services.
  Dashboard graph events should project these rows rather than invent a
  parallel event shape.

Recommended action:

- Keep run graph tables.
- Move status vocabulary out of persistence into runtime/shared.
- Continue the `node_id` -> `task_id` naming cleanup in code/contracts.

### Legacy `experiments` Table: Compatibility Only

```text
experiments  # BenchmarkDefinitionRecord
```

This table is the largest concept-debt item. It is not the canonical v2
definition table, but it is still active:

- `application/read_models/experiments.py` reads it as the legacy fallback path
  when no `ExperimentDefinition` row exists.
- cohort read models join through it.
- `complete_workflow.py` and `fail_workflow.py` update it when a run's
  `definition_id` points at a `BenchmarkDefinitionRecord`.
- `rl/rollout_service.py` still writes `BenchmarkDefinitionRecord` rows for RL
  rollout batches.
- `rest_api/test_harness.py` writes same-id legacy rows for cohort/dashboard
  compatibility.
- CLI experiment tag commands read its `experiment` tag.

Debt:

- The table name `experiments` collides with the v2 Python concept where an
  "experiment" is more like a composition/tag/grouping of runs, not the
  immutable definition itself.
- `BenchmarkDefinitionRecord` duplicates fields now represented by
  `ExperimentDefinition`, definition instances, object-bound task snapshots,
  and `RunRecord`.
- Several fields are pre-v2 selection defaults rather than canonical runtime
  state: `default_worker_team_json`, `default_evaluator_slug`,
  `default_model_target`, `sandbox_slug`, `dependency_extras_json`,
  `sample_selection_json`, and `design_json`.
- The `experiment` string tag is useful for grouping runs, but it is attached
  to a deprecated definition-shaped row instead of a v2 run grouping model.

Recommended action:

- Treat `BenchmarkDefinitionRecord` as compatibility-only, not a first-class v2
  schema.
- Stop new canonical authoring/launch paths from writing it.
- Move RL rollout and test-harness/dashboard compatibility off this table or
  isolate the writes behind an explicitly deprecated compatibility module.
- Replace CLI tag filtering with `RunRecord.experiment` before deleting.

### Cohort Tables: Compatibility Only, Frontend-Visible

```text
experiment_cohorts
experiment_cohort_stats
```

These are still live because the REST API and dashboard use them:

- `/cohorts` routes expose list/detail/update endpoints.
- `ExperimentCohortService` creates, updates, lists, and recomputes cohort
  stats.
- dashboard generated REST contracts still include cohort status.
- test harness resolves and seeds cohorts.

Debt:

- We have already agreed cohorts are deprecated in v2. They remain because the
  dashboard has not yet moved to the newer "experiment as collection/tag of
  runs" view.
- Cohort membership is not attached to canonical `ExperimentDefinition` or
  `RunRecord` directly. It flows through deprecated `BenchmarkDefinitionRecord`.
- `ExperimentCohortStats` denormalizes aggregate values that can be recomputed
  from runs/evaluations. It may be fine as a cache, but the ownership should be
  explicit.
- `ExperimentCohortStatus` is exported into frontend contracts even though the
  concept is scheduled for removal.

Recommended action:

- Keep until the dashboard refactor removes cohort UI and endpoints.
- Mark table/service/API/frontend contracts as deprecated compatibility.
- Do not build new runtime features on cohort membership.
- When deleting, delete the frontend contracts/routes and
  `BenchmarkDefinitionRecord.cohort_id` in the same cleanup slice.

### Run Records: Keep, But Identity Fields Need Cleanup

```text
runs
```

`RunRecord` is active and central. It anchors run status, provenance,
instance key, summaries, and lifecycle timestamps.

Debt:

- It carries both `definition_id` and `workflow_definition_id`. In canonical v2
  launches both point at `ExperimentDefinition.id`. In compatibility paths,
  `definition_id` may point at a `BenchmarkDefinitionRecord`, while
  `workflow_definition_id` points at `ExperimentDefinition`.
- Several callers now treat `workflow_definition_id` as the canonical
  definition id. Others still use `definition_id` to find legacy experiments or
  cohorts.
- `worker_team_json`, `evaluator_slug`, `sandbox_slug`,
  `dependency_extras_json`, and `assignment_json` are mostly launch/selection
  metadata from the pre-object-bound runtime. The active runtime reads
  worker/sandbox/evaluators from run-tier task snapshots, not these fields.
  Some fields still feed CLI/read-model displays or sandbox setup payloads.
- `summary_json` is a mixed bag: checkpoint metadata, final score/cost/error
  summaries, sandbox summaries, and other run-level facts can all land there.
  That makes it flexible but conceptually under-specified.
- `ergon_cli/commands/run.py` still filters through `RunRecord.experiment_id`,
  but the model no longer defines that field. That is an actual stale reference
  rather than just naming debt.

Recommended action:

- Keep `runs`.
- Make `RunRecord.definition_id` the canonical FK to `ExperimentDefinition` and
  delete `workflow_definition_id` after backfill.
- Mark `worker_team_json`, `evaluator_slug`, `sandbox_slug`, and
  `dependency_extras_json` compatibility/display-only in field descriptions.
- Keep `model_target` and `assignment_json` active.
- Replace CLI filtering that references `RunRecord.experiment_id`.
- Split or type run `summary_json` if it continues accumulating unrelated
  concepts.

### Task Execution Rows: Keep

```text
run_task_executions
```

This table is active and aligned with v2 execution telemetry. It records
attempts per `(run_id, task_id)`, status, sandbox id, final assistant message,
errors, and worker output.

Debt:

- `definition_worker_id` points at normalized definition worker rows even
  though object-bound workers are also serialized in task snapshots. This is
  still useful as provenance/read-model metadata, but it should be documented
  as derived/index/provenance rather than runtime source of truth.
- `worker_output_json` has an in-code TODO saying it may move behind a lazy
  `CriterionContext.worker_output()` accessor or dedicated output store. That
  is real concept debt: worker output is currently stored on execution rows
  because evaluation needs it.
- Status values come from `TaskExecutionStatus`, while graph node status has a
  separate vocabulary. That is okay if documented: execution status and graph
  status are different concepts. It becomes debt if code treats them
  interchangeably.

Recommended action:

- Keep.
- Document `definition_worker_id` as provenance.
- Resolve the worker output storage TODO in the criterion-context redesign.

### Evaluation Rows: Keep, But Summary Contract Should Move

```text
run_task_evaluations
```

This table is active. Evaluation jobs write rows, read models consume them, and
dashboard task evaluation events carry their DTOs.

Debt:

- `definition_evaluator_id` points to normalized definition evaluator rows
  while task snapshots also carry inline evaluators. This is still load-bearing
  for provenance, but it is duplicated conceptually.
- Evaluation summary schema lives in `persistence/telemetry/evaluation_summary.py`
  even though it describes evaluator/criterion semantics and is consumed by
  application/read-model code.
- `CreateTaskEvaluation` is an application command DTO living in persistence;
  PRD 01 deletes it rather than moving it because it only feeds a
  single-consumer repository that is also being deleted.

Recommended action:

- Keep `run_task_evaluations`.
- Move evaluation summary/command DTOs into application or shared.
- Document `definition_evaluator_id` as provenance/index derived from the
  object-bound evaluator.

### Resource Rows: Keep

```text
run_resources
```

This table is active and aligned with v2 append-only resource publication.

Debt:

- Resource publication policy currently lives partly under
  `infrastructure/sandbox/resource_publisher.py`.
- `kind` is a string validated against `RunResourceKind`; if resource kinds are
  product concepts, the enum should live with application/shared contracts and
  persistence should consume it.
- `file_path` points at local blob-store paths. That is practical but couples
  resource rows to one storage implementation. If blob backends expand, split
  URI/storage backend metadata.

Recommended action:

- Keep.
- Move publication semantics to application resources service as described in
  the infrastructure boundary audit.

### Context Event Rows: Keep, Alias File Delete Candidate

```text
run_context_events
```

The table is active: worker execution persists context chunks, run snapshots
read them, dashboard context events stream them, and RL extraction consumes
them.

Debt:

- `persistence/context/event_payloads.py` duplicates aliases over
  `ContextPartChunkLog`; the alias should be deleted and consumers should use
  `ContextPartChunkLog` directly.
- The model still imports context part contracts from
  `core.domain.generation.context_parts`, which we already plan to move to
  `core/shared/context_parts.py`.

Recommended action:

- Keep `run_context_events`.
- Delete or collapse `event_payloads.py` after the shared context contract
  move.

### Communication Tables: Keep, But Consider Domain Split

```text
threads
thread_messages
```

These are active through `CommunicationService`, run snapshots, and dashboard
thread message events.

Debt:

- They live inside the broad telemetry model file even though communication is
  an application domain with its own service and DTOs.
- Communication service runs direct SQL and emits dashboard events directly.
  That is application/infrastructure boundary debt rather than table death.

Recommended action:

- Keep.
- If telemetry models are split, move these table classes to a communication
  storage family.
- If communication grows, introduce an application communication repository.

### Training Tables: Keep If RL Training UI Remains

```text
training_sessions
training_metrics
```

These are read through REST `/runs/training/*` endpoints and dashboard training
UI components. I did not find active writers in this audit outside the model
comments, but the tables support a visible product surface.

Debt:

- The audit found REST reads and dashboard pages, but no in-repo production
  writer.
- `TrainingSession.experiment_definition_id` uses old experiment-definition
  naming but points at canonical `ExperimentDefinition`.
- Training status enum lives in persistence shared enums.

Recommended action:

- Treat `TrainingSession` and `TrainingMetric` as gated deletion candidates.
- If training observability remains a product surface, add/identify the writer
  and move the training DTOs to `views/training.py`.
- If training observability is stale, delete the tables, REST endpoints,
  generated contracts, and dashboard training UI together.

### Rollout Batch Tables: Keep

```text
rollout_batches
rollout_batch_runs
```

These are active through `RolloutService`. They provide durable batch state for
RL trainers and join rollout batches to generated run ids.

Debt:

- `RolloutService.submit()` still creates a `BenchmarkDefinitionRecord` per RL
  batch, then creates `RunRecord.definition_id=experiment.id` and
  `RunRecord.workflow_definition_id=request.definition_id`. That keeps the
  legacy `experiments` table alive for RL.
- Batch status literals are local to the persistence table validator, while RL
  request/response types also have `BatchStatus`.

Recommended action:

- Keep rollout batch tables.
- Stop using `BenchmarkDefinitionRecord` as RL batch provenance. Either make
  `RolloutBatch` the provenance container or add explicit run grouping metadata.
- Use one status contract for rollout batches.

### Sandbox WAL/Event Tables: Keep, But Clarify Ownership

```text
sandbox_command_wal_entries
sandbox_events
```

These are actively written by `PostgresSandboxEventSink` and read by e2e test
helpers. They are observability tables, not core runtime state.

Debt:

- `run_id` carries no FK and comments acknowledge teardown quirks where
  synthetic entries may use `run_id=task_id`.
- They live in telemetry models but are written directly from infrastructure.
  That is acceptable only if they remain observability/WAL rows, not product
  state.
- Sandbox event kinds are raw strings rather than typed event literals.

Recommended action:

- Keep as observability, but document that they are not runtime source of
  truth.
- Keep sandbox WAL/event rows in `persistence/telemetry/models.py` during this
  RFC; a later telemetry split may move them mechanically, without changing
  ownership.
- Fix the run-id teardown quirk before exposing sandbox WAL/event rows through
  dashboard/read-model views.

### Import Reducer Tables: Suspect

```text
run_reducers
run_reducer_footprints
run_drops_manifests
```

I found table definitions but no active production writer/reader in the scanned
code paths. The package docstring says they are for imported/public rollout
cards, but they appear disconnected from the current runtime.

There is also a concrete schema bug:

```python
node_id: UUID | None = Field(default=None, foreign_key="run_graph_nodes.id")
```

`RunGraphNode` no longer has an `id` column; its primary key is
`(run_id, task_id)`. This FK points at a non-existent schema concept.

Recommended action:

- Treat as suspect/high-priority verification.
- If unused, delete the tables/models before they become accidental API.
- If active outside this scan, rename the package around the real product
  concept and fix the FK to `(run_id, task_id)` or remove the node FK.

## Field-Level Concept Debt

### `definition_id` vs `workflow_definition_id`

Current meaning:

- `RunRecord.workflow_definition_id` is the canonical v2 definition id used to
  initialize/read a run.
- `RunRecord.definition_id` sometimes points at the same definition id, but in
  compatibility/RL flows can point at `BenchmarkDefinitionRecord.id`.

This is confusing enough that callers have to know which vintage of run they
are reading. It also makes `experiment_id`/`definition_id` naming in API DTOs
hard to reason about.

Target:

- choose one canonical definition FK for runtime;
- if legacy provenance is still needed, rename or isolate it as
  `legacy_experiment_record_id` or a compatibility table relation.

### `task_payload` vs `task_json`

Current meaning:

- `task_json` is the full object-bound task snapshot and is runtime-canonical.
- `task_payload` is payload-only compatibility/read convenience.

Target:

- keep only if readers need payload-specific access without loading the full
  object-bound task;
- otherwise plan deletion after all readers use `task_json`.

### Worker/Evaluator/Sandbox Selection Fields

Duplicated fields:

- `BenchmarkDefinitionRecord.default_worker_team_json`;
- `BenchmarkDefinitionRecord.default_evaluator_slug`;
- `BenchmarkDefinitionRecord.sandbox_slug`;
- `RunRecord.worker_team_json`;
- `RunRecord.evaluator_slug`;
- `RunRecord.sandbox_slug`;
- `RunTaskExecution.definition_worker_id`;
- `RunTaskEvaluation.definition_evaluator_id`;
- object-bound `Task.worker`, `Task.sandbox`, `Task.evaluators` inside
  `task_json`.

Target:

- object-bound task snapshots should drive runtime execution;
- normalized worker/evaluator ids may remain as provenance/index/read-model
  metadata;
- run/default fields should be display/compatibility only or deleted.

### `node_id` vs `task_id`

The schema largely moved to `task_id`, but code still uses `node_id` names in
application services, tests, CLI helpers, dashboard compatibility, and the
invalid reducer FK. This is naming debt and sometimes schema debt.

Target:

- use `task_id` for runtime graph identity everywhere public;
- reserve `node` only for internal graph row language if the team still wants
  it, but do not expose both names for the same id.

### Cohort Status And Experiment Tags

`ExperimentCohortStatus` and `BenchmarkDefinitionRecord.experiment` are both
frontend/CLI-visible grouping concepts, but neither matches the v2 statement
that experiments are a collection/tag of runs carried by Python composition.

Target:

- define one run grouping concept;
- move dashboard/CLI to it;
- delete cohort tables and legacy experiment tags after migration.

## Highest-Risk Findings

1. `RunReducer.node_id` references `run_graph_nodes.id`, but that column does
   not exist on the PR 16 schema.

2. `ergon_cli/commands/run.py` references `RunRecord.experiment_id`, but the
   model defines `definition_id` and `workflow_definition_id`, not
   `experiment_id`.

3. `BenchmarkDefinitionRecord` is deprecated by architecture but still active
   in RL rollout, cohort/dashboard compatibility, test harness, and CLI tags.
   It needs an explicit migration plan rather than ad hoc deletion.

4. Cohorts are deprecated by design but still frontend-visible through REST and
   generated dashboard contracts.

5. `RunRecord.definition_id` and `RunRecord.workflow_definition_id` encode two
   different eras of provenance in one active table.

## Suggested PR Slices

### PR A: Broken/Stale Reference Fixes

- Fix or delete `RunReducer.node_id` FK.
- Fix CLI run filtering that references `RunRecord.experiment_id`.
- Add schema/source tests that catch nonexistent FK target columns and stale ORM
  attribute references.

### PR B: Legacy Experiment Record Isolation

- Create a compatibility module around `BenchmarkDefinitionRecord` usages.
- Move RL rollout away from writing `BenchmarkDefinitionRecord`.
- Mark all remaining reads/writes as compatibility-only.
- Replace `BenchmarkDefinitionRecord.experiment` tags with
  `RunRecord.experiment`.

### PR C: Cohort Deprecation Migration

- Mark `/cohorts`, cohort DTOs, frontend contracts, and cohort tables as
  deprecated.
- Plan dashboard replacement around v2 run grouping.
- Delete cohort tables only after the dashboard no longer depends on them.

### PR D: Run Identity And Selection Field Cleanup

- Decide canonical `RunRecord` definition identity.
- Classify `worker_team_json`, `evaluator_slug`, `sandbox_slug`,
  `dependency_extras_json`, and `assignment_json`.
- Remove, rename, or document each as compatibility/display/provenance.

### PR E: Import Reducer Deletion

- Delete reducer/drop-manifest tables in PRD 01. The scanned code paths have no
  production writer/reader, and `RunReducer.node_id` points at a non-existent
  graph column.

### PR F: Training Tables Gate

- Keep training only if the implementation identifies or adds the production
  writer for `TrainingSession` and `TrainingMetric`.
- Otherwise remove the training dashboard/API surface with the tables.
