# Public API Folder Refactor Plan

Goal: make `ergon_core.api` small enough for students to understand while moving runtime, persistence, dashboard, cohort, run, and registry plumbing into `ergon_core.core`.

The public API should be an authoring kit: define benchmarks, tasks, workers, criteria, rubrics, and simple result objects. It should not expose database sessions, persistence handles, Inngest dispatch, cohort management, run lifecycle, or internal evaluation summaries.

## Proposed Folder Shape

```text
ergon_core/
   ergon_core/
      api/
         __init__.py
            # keep : only the student-facing authoring exports
            # export: Benchmark, BenchmarkTask, EmptyTaskPayload
            # export: Worker, WorkerContext, WorkerOutput
            # export: Criterion, CriterionResult, CriterionScoreSpec
            # export: Rubric, TaskEvaluationResult
            # export: CriteriaCheckError
            # stop exporting: Experiment, WorkerSpec, PersistedExperimentDefinition
            # consider hiding: Evaluator, EvaluationContext, BenchmarkDeps, DependencyError

         benchmark.py
            # keep : Benchmark as the public dataset/task generator base class
            # keep : type_slug, task_payload_model, build_instances()
            # keep : parse_task_payload()
            # simplify : evaluator_requirements() should become optional/advanced
            # move : dependency package checking to core/runtime/dependencies.py adapter
            # merge : onboarding_deps and required_packages into one simpler authoring metadata story

         task_types.py
            # keep : BenchmarkTask and EmptyTaskPayload
            # consider rename later : BenchmarkTask -> Task or TaskSpec
            # keep public because benchmarks, workers, and criteria all share it
            # do not expose: ExperimentDefinitionTask persistence model here

         worker.py
            # keep : Worker ABC and execute(task, context=...)
            # keep : optional from_buffer() only if resumption remains an author-facing extension point
            # move : default DB-backed get_output() implementation to core/runtime/output_extraction.py
            # move : ContextEventRepository/get_session imports out of public API
            # move : AssistantTextPart/ContextPartChunk dependency behind a smaller public streaming type or an advanced namespace
            # simplify : base Worker should not know how context events are persisted

         worker_context.py
            # keep : WorkerContext as the minimal execution context passed to Worker.execute()
            # simplify : expose only run_id, task_id, execution_id, sandbox_id, metadata if possible
            # move inward : definition_id and node_id if only runtime/delegation needs them
            # consider : a separate internal CoreWorkerContext for graph/runtime identity

         results.py
            # keep : WorkerOutput
            # keep : CriterionScoreSpec
            # keep : CriterionResult
            # keep : TaskEvaluationResult
            # keep or move advanced : CriterionObservation and CriterionObservationMessage
            # move : JsonObject import from core into a public local alias/type
            # merge : align CriterionResult fields with core EvaluationSummary conversion in one adapter

         criterion.py
            # keep : Criterion ABC
            # keep : evaluate(context) -> CriterionResult
            # move : dependency package checking to core validation helper
            # simplify : criterion authors should not need to import core runtime protocols

         evaluation_context.py
            # keep temporarily : EvaluationContext for compatibility
            # replace with : CriterionContext or EvaluationContext with public helper methods
            # move : CriterionRuntime Protocol import to core/runtime/evaluation/protocols.py only
            # hide : sandbox manager/runtime internals behind context.execute_code(), context.read_resource(), etc.
            # eventual delete : if Criterion can receive a simpler public CriterionContext

         evaluator.py
            # keep : Rubric as the common public evaluation concept
            # consider advanced : Evaluator ABC moves to api/advanced/evaluator.py or core/runtime/evaluation
            # merge : default weighted aggregation remains Rubric
            # move : dynamic evaluator orchestration details to core/runtime/services/rubric_evaluation_service.py
            # clarify : Rubric = author-facing grouping of criteria; evaluator service = internal runner

         errors.py
            # keep : CriteriaCheckError
            # consider move : DependencyError to core/runtime/dependencies.py unless public callers catch it

         benchmark_deps.py
            # merge : into Benchmark metadata or move to api/onboarding.py
            # keep temporarily : compatibility for ergon_cli/onboarding/profile.py and built-in benchmark declarations
            # eventual delete : once onboarding reads a simpler Benchmark.onboarding field

         experiment.py
            # move to core/runtime/composition/experiment.py or core/runtime/services/experiment_composition.py
            # reason : binds benchmark + worker specs + evaluators + assignments for persistence
            # reason : persist() calls core ExperimentPersistenceService
            # public replacement : a simple CLI/application facade, not a student authoring primitive
            # eventual delete from top-level api

         worker_spec.py
            # move to core/runtime/composition/worker_spec.py
            # reason : config-time descriptor for registry lookup, not worker authoring
            # reason : validate_spec() imports ergon_builtins.registry.WORKERS
            # public replacement : CLI accepts worker_slug/model and core builds WorkerSpec internally
            # eventual delete from top-level api

         handles.py
            # move to core/runtime/services/experiment_handles.py or core/runtime/composition/handles.py
            # reason : PersistedExperimentDefinition is a persistence/run launch handle
            # public replacement : CLI-facing RunHandle/DefinitionHandle returned by core facade
            # eventual delete from top-level api
```

```text
ergon_core/
   ergon_core/
      core/
         runtime/
            composition/
               __init__.py
                  # create : internal composition exports for CLI/core

               experiment.py
                  # move from api/experiment.py
                  # keep : Experiment composition root if core still needs object-first persistence
                  # change : persist() should become service-owned, not a method on Experiment

               worker_spec.py
                  # move from api/worker_spec.py
                  # keep : WorkerSpec registry descriptor
                  # keep : validate_spec() registry lookup here, away from public API

               handles.py
                  # move from api/handles.py
                  # keep : PersistedExperimentDefinition or rename to WorkflowDefinitionHandle

            output_extraction.py
               # create : default worker output extraction from context events
               # move from api/worker.py : ContextEventRepository/get_session/AssistantTextPart logic
               # used by : core/runtime/inngest/worker_execute.py

            dependencies.py
               # keep : check_packages()
               # add : validate_component_dependencies(component_type, slug, packages, install_hint)
               # public ABCs call this only through small wrappers, or core validates before launch

            evaluation/
               protocols.py
                  # keep : CriterionRuntime internal protocol
                  # no public api imports should depend on this directly

               context.py
                  # create or rename : internal TaskEvaluationContext/CriterionContext live here
                  # owns : sandbox/runtime details for criterion execution

               adapters.py
                  # create : convert public CriterionResult into persisted EvaluationSummary entries
                  # merge logic currently split between public results and persistence summary models

               evaluation_schemas.py
                  # keep : internal CriterionSpec, TaskEvaluationContext, CriterionContext
                  # maybe rename : criterion_specs.py if it remains evaluation-engine only

            services/
               public_api_facade.py
                  # create : CLI/application facade for common operations
                  # owns : define benchmark experiment, persist definition, create cohort/run, dispatch, poll
                  # goal : CLI should import one core facade instead of many core services/models

               experiment_persistence_service.py
                  # keep : writes Experiment/BenchmarkTask object graph to immutable definition rows
                  # adjust imports : read Experiment and WorkerSpec from core/runtime/composition

               experiment_definition_service.py
                  # keep : create ExperimentRecord sample selections
                  # clarify name : this creates experiment records, not immutable workflow definitions
                  # possible rename later : benchmark_experiment_service.py

               experiment_launch_service.py
                  # keep : materializes runs for defined ExperimentRecord rows
                  # adjust imports : use core composition types, not public api Experiment/WorkerSpec

               rubric_evaluation_service.py
                  # keep : internal service runner
                  # clarify : not the same concept as public Rubric
                  # maybe rename : task_evaluation_service.py

               evaluation_persistence_service.py
                  # keep : persistence of evaluation summaries
                  # move conversion from public-ish result shapes into runtime/evaluation/adapters.py

               cohort_service.py
                  # keep : cohorts are operator/runtime grouping, not student API
                  # expose via facade only for CLI/dashboard

               run_service.py
                  # keep : runs are runtime telemetry/lifecycle, not student API
                  # expose via facade only for CLI/dashboard
```

```text
ergon_cli/
   ergon_cli/
      composition/
         __init__.py
            # delete or shrink substantially
            # current : imports public Experiment + WorkerSpec
            # move : build_experiment() logic to core/runtime/composition or services/public_api_facade.py
            # replacement : CLI passes slugs/options to core facade

      commands/
         benchmark.py
            # keep : command parsing and rendering only
            # move inward : create_run, WorkflowStartedEvent, inngest_client, RunRecord polling
            # replace with : public_api_facade.run_benchmark(...)
            # keep : setup benchmark E2B template logic unless moved to onboarding service

         experiment.py
            # keep : command parsing/rendering
            # replace multiple core service imports with one facade import

         run.py
            # keep : command parsing/rendering
            # replace direct RunRecord/run_service access with one run facade

         workflow.py
            # keep : command parsing/rendering
            # replace direct workflow_service/db access with facade if possible

      onboarding/
         profile.py
            # keep : onboarding profile behavior
            # change later : read Benchmark.onboarding metadata instead of BenchmarkDeps directly
```

```text
ergon_builtins/
   ergon_builtins/
      benchmarks/
         */benchmark.py
            # keep public imports : Benchmark, BenchmarkTask, EmptyTaskPayload
            # update : BenchmarkDeps if moved/merged
            # no direct dependency on core persistence or run concepts

         */rubric.py
            # keep public imports : Rubric, CriterionResult, TaskEvaluationResult, BenchmarkTask
            # if Evaluator moves advanced/internal, custom rubrics should still subclass Rubric

         */criterion.py
            # keep public imports : Criterion, CriterionResult, CriterionScoreSpec
            # update : EvaluationContext -> simpler CriterionContext if introduced

      workers/
         */*.py
            # keep public imports : Worker, WorkerContext, WorkerOutput, BenchmarkTask
            # update : streaming chunk type if ContextPartChunk is hidden or rehomed

      registry.py
         # keep : plugin registry for built-ins
         # core composition validates WorkerSpec/Benchmark/Evaluator slugs against this
         # public API should not import this registry directly
```

## Concept Merges And Renames

### Experiment Concepts

Current concepts:

- `api.Experiment`: object graph for benchmark + workers + evaluators + assignments.
- `core.persistence.telemetry.ExperimentRecord`: cohort/sample-selection record.
- `core.persistence.definitions.ExperimentDefinition`: immutable workflow definition rows.

Plan:

- Keep `ExperimentDefinition` as a core persistence name.
- Consider renaming `ExperimentRecord` service language to `BenchmarkExperiment` or `ExperimentPlan` later, because it is not the immutable workflow definition.
- Move public `Experiment` into core composition, or rename it `WorkflowDefinitionDraft` if it remains object-first.
- Do not ask students to learn all three names.

### Worker Concepts

Current concepts:

- `Worker`: execution-ready authoring base class.
- `WorkerSpec`: config-time registry descriptor.
- `ExperimentDefinitionWorker`: persisted worker binding row.

Plan:

- Keep `Worker` public.
- Move `WorkerSpec` into core composition.
- Keep `ExperimentDefinitionWorker` internal.
- CLI should accept `worker_slug` and `model`; core creates `WorkerSpec`.

### Evaluation Concepts

Current concepts:

- `Criterion`: atomic authoring unit.
- `Rubric`: fixed-list `Evaluator` with aggregation.
- `Evaluator`: abstract dynamic evaluator.
- `RubricEvaluationService`: runtime service that executes criteria and aggregates.
- `CriterionResultEntry` / `EvaluationSummary`: persisted dashboard schema.

Plan:

- Keep `Criterion` and `Rubric` public.
- Keep `Evaluator` advanced or internal unless third-party dynamic evaluators are required.
- Rename or document `RubricEvaluationService` as internal task evaluation runner.
- Keep `EvaluationSummary` internal.
- Add one adapter that maps `CriterionResult`/`TaskEvaluationResult` to persisted summary rows.

### Task Concepts

Current concepts:

- `BenchmarkTask`: author-facing task object generated by a benchmark.
- `ExperimentDefinitionTask`: persisted definition row.
- `RunTaskExecution`: runtime execution telemetry row.

Plan:

- Keep `BenchmarkTask` public for now.
- Consider future alias `Task = BenchmarkTask` for student docs.
- Keep persistence/runtime task rows internal.
- Core adapters convert public task specs into definition rows.

### Cohort And Run Concepts

Current concepts:

- Cohorts and runs are not in `ergon_core.api`, but CLI imports core services/models directly.
- `ExperimentCohort`, `ExperimentCohortStats`, `RunRecord`, `RunTaskExecution`, `RunTaskEvaluation` are operator/runtime concepts.

Plan:

- Keep cohorts and runs out of the student authoring API.
- Add a CLI/application facade so built-in CLI can use cohorts/runs without importing persistence models, Inngest events, or low-level services.
- Dashboard/API routers can still use detailed core services and DTOs.

## Compatibility Strategy

1. Add architecture tests for the intended boundary before moving code.
2. Keep compatibility re-exports for one refactor window:
   - `ergon_core.api.experiment.Experiment`
   - `ergon_core.api.worker_spec.WorkerSpec`
   - `ergon_core.api.handles.PersistedExperimentDefinition`
   - `ergon_core.api.benchmark_deps.BenchmarkDeps`
3. Update `ergon_cli` and `ergon_core.core` imports first so internal code no longer depends on public API for internal composition.
4. Update `ergon_builtins` imports only after the public authoring surface is stable.
5. Remove compatibility shims once tests and docs no longer reference moved symbols.

## Suggested Implementation Order

```text
phase_1_boundary_tests/
   tests/unit/architecture/test_public_api_boundaries.py
      # add forbidden import checks for api -> core.persistence, core.runtime.evaluation.protocols, core.generation
      # add explicit expected top-level public exports

phase_2_worker_runtime_split/
   ergon_core/ergon_core/api/worker.py
      # keep Worker ABC only
      # remove DB/context event imports

   ergon_core/ergon_core/core/runtime/output_extraction.py
      # create default output extraction helper

   ergon_core/ergon_core/core/runtime/inngest/worker_execute.py
      # use output_extraction helper after worker.execute()

phase_3_composition_move/
   ergon_core/ergon_core/core/runtime/composition/
      # create experiment.py, worker_spec.py, handles.py

   ergon_core/ergon_core/api/
      # leave temporary import shims for Experiment, WorkerSpec, PersistedExperimentDefinition

   ergon_cli/ergon_cli/composition/__init__.py
      # migrate logic or shrink to facade call

phase_4_cli_facade/
   ergon_core/ergon_core/core/runtime/services/public_api_facade.py
      # create stable CLI-facing functions/classes

   ergon_cli/ergon_cli/commands/*.py
      # replace direct core service/model/event imports where practical

phase_5_evaluation_simplification/
   ergon_core/ergon_core/api/evaluation_context.py
      # replace raw runtime protocol exposure with public context methods

   ergon_core/ergon_core/core/runtime/evaluation/adapters.py
      # centralize result-to-summary conversion

   ergon_core/ergon_core/api/evaluator.py
      # make Rubric primary; move Evaluator to advanced/internal if desired

phase_6_cleanup/
   ergon_core/ergon_core/api/__init__.py
      # remove moved concepts from top-level exports

   docs/
      # update student-facing examples to import only the authoring kit
```

## Desired Final Student-Facing Mental Model

```text
I define a Benchmark.
The Benchmark returns Tasks.
A Worker solves each Task.
A Criterion checks the output.
A Rubric combines Criteria into a score.
Ergon core handles experiments, definitions, cohorts, runs, persistence, dispatch, and dashboards.
```
