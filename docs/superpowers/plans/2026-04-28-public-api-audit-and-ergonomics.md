# Public API Audit And Ergonomics Working Doc

This is a working document for deciding what belongs in `ergon_core.api`, what should move inward to `ergon_core.core`, and what concepts can be merged so the API is easier for students and benchmark authors to use.

The goal is not to make the public API artificially tiny. The goal is to make it honest. A public symbol should either be:

- something a benchmark author uses to describe work,
- something a worker author uses to solve work,
- something an evaluator author uses to score work,
- or a deliberately documented advanced extension point.

Everything else should probably be core, CLI, dashboard, persistence, or runtime plumbing.

## Current Public API Root

`ergon_core.api.__all__` currently exports:

```python
Benchmark
BenchmarkDeps
BenchmarkTask
Criterion
CriterionResult
CriteriaCheckError
DependencyError
EvaluationContext
Evaluator
Experiment
EmptyTaskPayload
PersistedExperimentDefinition
Rubric
TaskEvaluationResult
Worker
WorkerContext
WorkerOutput
WorkerSpec
```

Submodule-only public-ish symbols currently used or plausibly imported:

```python
CriterionScoreSpec
CriterionObservation
CriterionObservationMessage
```

Important existing boundary tests:

- `tests/unit/api/test_public_api_imports.py` already asserts that runtime/tooling concepts like `RunResourceView`, `CriterionRuntime`, `CommandResult`, `SandboxResult`, and `Tool` are not exposed at the root.
- `tests/unit/architecture/test_public_api_boundaries.py` already protects against restoring deleted facade modules like `api.generation`, `api.json_types`, `api.run_resource`, `api.criterion_runtime`, `api.dependencies`, and `api.types`.

That means the codebase already wants `ergon_core.api` to stay authoring-scoped. The current issue is that some exported authoring-looking objects still pull runtime/persistence concepts through the side door.

## Current Mental Model

The current public API effectively asks users to understand this:

```text
Benchmark -> BenchmarkTask -> Experiment -> WorkerSpec -> persisted definition -> run
Worker -> WorkerContext -> streamed core generation chunks -> WorkerOutput
Criterion -> EvaluationContext -> core CriterionRuntime -> CriterionResult
Evaluator/Rubric -> TaskEvaluationResult
```

The student-facing model we probably want is closer to:

```text
Benchmark -> Task
Worker solves Task
Criterion checks WorkerOutput
Rubric combines Criteria
Core handles experiments, runs, cohorts, persistence, dispatch, and dashboards
```

## Usage Map At A Glance

### CLI

The built-in CLI imports only a small part of `ergon_core.api` directly:

- `ergon_cli/ergon_cli/composition/__init__.py`
  - imports `Experiment`
  - imports `WorkerSpec`
- `ergon_cli/ergon_cli/onboarding/profile.py`
  - imports `BenchmarkDeps`

The CLI otherwise reaches straight into `ergon_core.core` for:

- DB setup and sessions,
- telemetry models such as `RunRecord`,
- `create_run`,
- cohort resolution,
- Inngest event dispatch,
- experiment define/launch/read services,
- workflow services,
- runtime settings.

This is a useful signal. `ergon_core.api` is not really the CLI API today. The CLI already operates at the application/runtime layer.

### Built-ins

`ergon_builtins` uses the public API heavily as an extension-authoring kit:

- Benchmarks subclass `Benchmark` and create `BenchmarkTask`.
- Workers subclass `Worker` and receive `WorkerContext`.
- Criteria subclass `Criterion`, receive `EvaluationContext`, and return `CriterionResult`.
- Rubrics subclass `Rubric` and return `TaskEvaluationResult`.
- Registries type their maps as `Benchmark`, `Evaluator`, and `Worker`.
- Onboarding metadata uses `BenchmarkDeps`.

This is the strongest argument that `Benchmark`, `BenchmarkTask`, `Worker`, `WorkerContext`, `WorkerOutput`, `Criterion`, `CriterionResult`, `CriterionScoreSpec`, `Rubric`, and `TaskEvaluationResult` should remain public or have very deliberate replacements.

### Core Runtime

Core runtime imports public API types in several places:

- `core/runtime/inngest/worker_execute.py`
  - uses `BenchmarkTask`, `EmptyTaskPayload`, `WorkerContext`
- `core/runtime/evaluation/inngest_executor.py`
  - uses `Criterion`, `EvaluationContext`, `CriterionResult`, `WorkerOutput`, `BenchmarkTask`
- `core/runtime/evaluation/evaluation_schemas.py`
  - uses `Criterion`
- `core/runtime/services/rubric_evaluation_service.py`
  - uses `Evaluator`, `CriterionResult`, `TaskEvaluationResult`, `BenchmarkTask`
- `core/runtime/services/experiment_persistence_service.py`
  - uses `Rubric`, `PersistedExperimentDefinition`, and type-checks `Experiment`
- `core/runtime/services/experiment_launch_service.py`
  - uses `Benchmark`, `Evaluator`, `Experiment`, `PersistedExperimentDefinition`, `BenchmarkTask`, `WorkerSpec`
- `core/runtime/services/experiment_definition_service.py`
  - uses `Benchmark`, `BenchmarkTask`
- `core/runtime/services/run_service.py`
  - uses `PersistedExperimentDefinition`

Some of that is fine: core runtime naturally consumes public authoring objects. But the reverse direction is more concerning: public API modules also import core runtime/persistence modules.

### Tests

Tests use almost every current public type:

- API contract tests cover imports and public API boundary behavior.
- Runtime tests instantiate criteria, rubrics, contexts, tasks, and result models.
- Built-in benchmark tests instantiate `Benchmark`, `BenchmarkTask`, `BenchmarkDeps`, `EvaluationContext`, `WorkerOutput`, and result models.
- Worker tests use `WorkerContext`, `BenchmarkTask`, and `EmptyTaskPayload`.
- Runtime service tests use `PersistedExperimentDefinition`.

This means simplification should be staged. Move internal users first, leave compatibility imports where useful, then adjust tests around the intended boundary.

## Public File Inventory

```text
ergon_core/ergon_core/api/
   __init__.py
      exports the object-first public surface

   benchmark.py
      Benchmark base class
      currently also validates required packages via core runtime dependencies

   benchmark_deps.py
      BenchmarkDeps onboarding metadata

   task_types.py
      EmptyTaskPayload
      BenchmarkTask

   worker.py
      Worker base class
      currently imports core generation chunk types
      currently reads persisted context events to build default output

   worker_context.py
      WorkerContext execution identity model

   worker_spec.py
      WorkerSpec config-time registry descriptor
      imports ergon_builtins registry during validation

   criterion.py
      Criterion base class
      currently validates required packages via core runtime dependencies

   evaluation_context.py
      EvaluationContext for criteria
      currently exposes core CriterionRuntime protocol as a field

   evaluator.py
      Evaluator base class
      Rubric concrete class
      currently validates required packages via core runtime dependencies

   results.py
      WorkerOutput
      CriterionScoreSpec
      CriterionObservationMessage
      CriterionObservation
      CriterionResult
      TaskEvaluationResult
      currently imports core JsonObject

   experiment.py
      Experiment composition root
      validates object graph
      persists through core ExperimentPersistenceService

   handles.py
      PersistedExperimentDefinition handle returned by Experiment.persist()
      imports core utcnow helper

   errors.py
      DependencyError
      CriteriaCheckError
```

## Symbol By Symbol Review

### `Benchmark`

Current role:

- Public base class for benchmark authors.
- Owns `type_slug`, `task_payload_model`, `build_instances()`, `evaluator_requirements()`, `parse_task_payload()`, and dependency validation.

Where used:

- Built-in benchmarks: MiniF2F, SWE-Bench Verified, ResearchRubrics, GDPEval.
- Core experiment definition and launch services.
- Registries type benchmark constructors.
- Tests for benchmark contracts and runtime services.

Keep in public API?

- Yes.

Concerns:

- The name is good for benchmark authors.
- `build_instances()` returning `Mapping[str, Sequence[BenchmarkTask]]` introduces "instance" as an extra concept. That may be necessary for benchmark datasets, but it is one more noun.
- `evaluator_requirements()` exposes evaluator slot binding to benchmark authors.
- `validate()` imports `core.runtime.dependencies.check_packages`.

Possible cleanup:

- Keep `Benchmark` public.
- Consider making `evaluator_requirements()` advanced or replacing it with a simpler `default_evaluator_slots = ("default",)` class var.
- Decide whether benchmark authors should declare dependency metadata as:
  - `required_packages` plus `install_hint`,
  - `onboarding_deps`,
  - or one consolidated `requirements` object.
- Move dependency validation implementation inward so `api.benchmark` does not import core runtime.

Decision question:

- Should a student writing a benchmark need to know about evaluator binding keys, or should benchmarks just produce tasks and let the experiment/CLI layer attach rubrics?

### `BenchmarkTask` And `EmptyTaskPayload`

Current role:

- `BenchmarkTask` is the public task object passed to workers and criteria.
- `EmptyTaskPayload` is the default Pydantic payload when a benchmark has no structured task data.

Where used:

- All built-in benchmarks create `BenchmarkTask`.
- Built-in workers consume `BenchmarkTask`.
- Built-in criteria and rubrics receive task objects.
- Core runtime reconstructs `BenchmarkTask` from persisted task rows.
- Many tests instantiate it directly.

Keep in public API?

- Yes.

Concerns:

- The name `BenchmarkTask` is precise but slightly more formal than necessary for students.
- It contains `instance_key`, `parent_task_slug`, `dependency_task_slugs`, and `evaluator_binding_keys`, which are runtime/workflow concepts mixed into the authoring task model.

Possible cleanup:

- Keep `BenchmarkTask` for compatibility.
- Consider a friendlier alias:

```python
Task = BenchmarkTask
```

- Longer term, split:
  - public `Task`: slug, description, payload,
  - advanced/internal `WorkflowTaskSpec`: parent/dependencies/evaluator bindings/instance key.

Decision question:

- Are task dependencies and evaluator bindings part of the beginner benchmark-authoring story, or are they an advanced workflow story?

### `Worker`

Current role:

- Public base class for workers.
- Authors implement `execute(task, context=...)`.
- `execute()` yields `ContextPartChunk` objects.
- Default `get_output()` reads context events from the database and extracts the last assistant text.

Where used:

- Built-in ReAct worker and training stub worker subclass it.
- Smoke fixtures subclass it.
- Registries type worker constructors.
- Core runtime instantiates workers in `worker_execute.py`.
- Tests assert worker contracts.

Keep in public API?

- Yes, but slim it down.

Concerns:

- `api.worker` imports:
  - `core.generation.AssistantTextPart`
  - `core.generation.ContextPartChunk`
  - `core.persistence.context.repository.ContextEventRepository`
  - `core.persistence.shared.db.get_session`
  - `core.runtime.dependencies.check_packages`
- That means the public base class knows persistence and generation internals.
- Students writing a worker must understand streaming chunks, not just "return an answer".

Possible cleanup:

- Keep `Worker` public.
- Move DB-backed default output extraction to core runtime, probably near `worker_execute.py`.
- Decide whether beginner workers can implement a simpler method:

```python
async def run(self, task: Task, context: WorkerContext) -> WorkerOutput:
    ...
```

while advanced workers implement streaming:

```python
async def execute(self, task: Task, *, context: WorkerContext) -> AsyncGenerator[ContextPartChunk, None]:
    ...
```

- If streaming remains public, either:
  - intentionally export the chunk type as an advanced public type,
  - or define a small public event/chunk model that core adapts into context events.

Decision question:

- Should the student-facing worker API be "return a WorkerOutput" first, with streaming as advanced, or should all workers remain streaming-first?

### `WorkerContext`

Current role:

- Public model passed to `Worker.execute()`.
- Contains `run_id`, `definition_id`, `task_id`, `execution_id`, `sandbox_id`, `node_id`, and metadata.

Where used:

- Built-in workers.
- Built-in tools such as workflow CLI tooling.
- Core runtime worker execution.
- Tests.

Keep in public API?

- Yes, but possibly with fewer fields.

Concerns:

- `definition_id` and `node_id` are graph/runtime concepts.
- `task_id` is nullable for dynamic subtasks, while `execution_id` is always present. That distinction is important to core but awkward to explain to students.

Possible cleanup:

- Public `WorkerContext` could expose:
  - `run_id`
  - `task_id` or `execution_id`
  - `sandbox_id`
  - `metadata`
- Internal `CoreWorkerContext` could add:
  - `definition_id`
  - `node_id`
  - static-vs-dynamic task identity.

Decision question:

- Which IDs do worker authors actually need in normal code? If most only need `sandbox_id` and maybe `execution_id`, hide the rest.

### `WorkerOutput`

Current role:

- Public result model for worker completion.
- Contains `output`, `success`, and metadata.

Where used:

- Built-in workers return it.
- Criteria receive it through `EvaluationContext`.
- Core evaluation executor wraps agent reasoning into it.
- Tests instantiate it.

Keep in public API?

- Yes.

Concerns:

- Field name `output` is generic but probably fine.
- `success` is useful but can overlap with runtime execution status.

Possible cleanup:

- Keep as-is unless we introduce a simpler non-streaming worker API.
- If worker runtime status and worker semantic success diverge, document that `success` means "worker produced a usable answer", not "the process did not crash".

Decision question:

- Do we want `WorkerOutput.output` to stay a single string, or should structured outputs become first-class?

### `Criterion`

Current role:

- Public base class for atomic evaluation units.
- Authors implement `evaluate(context) -> CriterionResult`.

Where used:

- Built-in criteria for SWE-Bench, MiniF2F, ResearchRubrics, generic code checks, LLM judge, sandbox file check.
- Smoke fixtures.
- Core evaluation executor.
- Core evaluation schemas store `Criterion` in `CriterionSpec`.
- Tests.

Keep in public API?

- Yes.

Concerns:

- `Criterion.evaluate()` depends on `EvaluationContext`, which currently exposes core runtime capability plumbing.
- `validate()` imports core dependency checking.

Possible cleanup:

- Keep `Criterion` public.
- Simplify the context it receives.
- Move dependency checking inward or expose it as a small public helper independent of `core`.

Decision question:

- Should criteria own sandbox/resource access directly through context helper methods, or should they receive a separate capability object?

### `EvaluationContext`

Current role:

- Public context passed to `Criterion.evaluate()`.
- Contains run/task/execution IDs, `BenchmarkTask`, `WorkerOutput`, sandbox ID, metadata, and optional runtime capability.

Where used:

- Built-in criteria.
- Smoke criteria.
- Core Inngest criterion executor.
- Tests for runtime injection and criterion contracts.

Keep in public API?

- Probably yes short-term, but redesign it.

Concerns:

- It imports `core.runtime.evaluation.protocols.CriterionRuntime`.
- The public field `runtime` means criterion authors can see an internal protocol rather than a stable student-facing capability.
- It duplicates some identity with `WorkerContext`.

Possible cleanup:

- Keep the name `EvaluationContext` if we want stability.
- Change the implementation so it owns public helper methods:

```python
await context.execute_code("pytest -q")
await context.read_resource("answer.txt")
await context.read_resource_by_id(resource_id)
```

- Store the internal runtime in a private field, not as a public typed protocol.
- Or rename to `CriterionContext` if we want "criterion evaluates with criterion context" instead of a broader evaluation context.

Decision question:

- Is `EvaluationContext` the right public name, or is `CriterionContext` easier for students?

### `CriterionScoreSpec`

Current role:

- Public-ish score range model for criteria.
- Not exported from `ergon_core.api.__all__`, but imported from `ergon_core.api.results` by tests and built-ins.

Where used:

- Criteria constructors.
- MiniF2F proof verification.
- Code check and LLM judge criteria.
- Runtime tests.

Keep in public API?

- Yes, if criteria remain configurable with score ranges.

Concerns:

- It is public by usage but not top-level exported.
- If top-level exports are the documented API, this mismatch is confusing.

Possible cleanup:

- Either export it at the root:

```python
from ergon_core.api import CriterionScoreSpec
```

- Or document `ergon_core.api.results.CriterionScoreSpec` as advanced.

Decision question:

- Do we want all common authoring types available from `ergon_core.api`, or do we want submodules for less common result/config types?

### `CriterionResult`

Current role:

- Public result of a single criterion.
- Includes score, pass/fail, weight, feedback, evidence IDs, observations, errors, and metadata.

Where used:

- Built-in criteria return it.
- Rubrics aggregate it.
- Core evaluation executor returns it from each criterion step.
- Evaluation persistence converts it into persisted summaries.
- Tests.

Keep in public API?

- Yes.

Concerns:

- It is fairly large for students.
- It overlaps with internal `CriterionResultEntry` in `core.persistence.telemetry.evaluation_summary`.

Possible cleanup:

- Keep public `CriterionResult`.
- Keep persisted `CriterionResultEntry` internal.
- Centralize conversion in a core adapter so authors only learn `CriterionResult`.
- Consider helper constructors:

```python
CriterionResult.pass_(slug="...", score=1.0, feedback="...")
CriterionResult.fail(slug="...", feedback="...")
```

Decision question:

- Should we add helper constructors to reduce boilerplate in student-written criteria?

### `CriterionObservation` And `CriterionObservationMessage`

Current role:

- Structured observation models nested inside `CriterionResult`.
- Capture prompt messages, evidence resource/action IDs, model details, and output.

Where used:

- ResearchRubrics judge criterion and LLM judge criterion.
- Evaluation summary persistence imports `CriterionObservation`.
- Tests likely inspect summary contracts.

Keep in public API?

- Keep in `results.py`, but maybe not root export.

Concerns:

- This is useful for advanced LLM-as-judge and audit trails.
- It may be too detailed for the beginner path.
- It imports or depends on JSON object typing from core through `results.py`.

Possible cleanup:

- Keep as advanced result detail.
- Move JSON type alias local to public API or use `dict[str, object]` style.

Decision question:

- Do students need to produce structured observations, or is this mainly for built-in LLM judges and dashboard evidence?

### `Rubric`

Current role:

- Public concrete evaluator with a fixed list of criteria.
- Aggregates criterion scores with weighted average.

Where used:

- Built-in rubrics.
- Smoke rubrics.
- Core persistence checks whether an evaluator is a `Rubric` to snapshot criteria names.
- Core runtime service evaluates via `Evaluator` interface.
- Tests.

Keep in public API?

- Yes.

Concerns:

- It subclasses `Evaluator`, so users see both `Evaluator` and `Rubric`.
- Public `Rubric` is simple, but `RubricEvaluationService` in core has a similar name and is a runtime runner.
- Built-ins like GDPEval subclass `Rubric` but implement staged gating, which stretches the fixed-list weighted-average base concept.

Possible cleanup:

- Make `Rubric` the primary student-facing evaluation concept.
- Consider an explicit `WeightedRubric` name if we add multiple rubric types.
- Rename core `RubricEvaluationService` to `TaskEvaluationService` or `EvaluationRunner` to avoid confusing public rubric with internal service.

Decision question:

- Is `Rubric` always "a thing with criteria", or should `Evaluator` be the primary abstraction and `Rubric` just one implementation?

### `Evaluator`

Current role:

- Public ABC for objects that select criteria for a task and aggregate criterion results.
- `Rubric` subclasses it.

Where used:

- Built-in registry typing.
- Core evaluation service accepts `Evaluator`.
- Core launch service builds evaluator bindings.
- Custom built-in rubrics inherit through `Rubric`.

Keep in public API?

- Maybe.

Concerns:

- It is a powerful extension point, but it adds another noun for students.
- Most authors probably need `Rubric`, not arbitrary dynamic evaluators.
- ResearchRubrics does need task-specific criteria via `criteria_for(task)`, which is an evaluator behavior.

Possible cleanup:

- Keep `Evaluator` for advanced users.
- Do not feature it in beginner docs.
- Potentially move it to `ergon_core.api.advanced` while `Rubric` stays root-exported.
- Or keep it root-exported because registries and dynamic task-specific rubrics already rely on it.

Decision question:

- Do we want external users to write custom dynamic evaluators, or only criteria and rubrics?

### `TaskEvaluationResult`

Current role:

- Public aggregated result for one task after criteria run.

Where used:

- Rubrics return it.
- Core runtime persists it.
- Tests.

Keep in public API?

- Yes if custom rubrics/evaluators remain public.

Concerns:

- It overlaps with `EvaluationSummary`, which is internal persisted/dashboard state.

Possible cleanup:

- Keep public.
- Make `EvaluationSummary` clearly internal.
- Add adapter for persistence.

Decision question:

- Should rubric authors directly construct `TaskEvaluationResult`, or should Rubric have simpler aggregation hooks?

### `Experiment`

Current role:

- Public composition root binding a benchmark, worker specs, evaluator bindings, assignments, and metadata.
- Validates the object graph.
- Persists itself by lazy-importing `ExperimentPersistenceService` from core.

Where used:

- CLI composition builds `Experiment`.
- Core launch service builds a temporary single-sample `Experiment`.
- Core persistence service type-checks it.
- Tests cover launch/persistence behavior.

Keep in public API?

- Open question.

Argument to keep:

- It is a natural word for users: "I want to run an experiment."
- It provides one object that composes benchmark, workers, and evaluators.
- CLI composition already uses it.

Argument to move or de-emphasize:

- It is not an authoring primitive like `Benchmark`, `Worker`, or `Criterion`.
- It exposes binding keys, assignments, evaluator maps, and worker specs.
- `persist()` makes public API depend on core persistence.
- There are already core concepts called `ExperimentRecord` and `ExperimentDefinition`, so the word "Experiment" is overloaded.

Possible cleanup:

- Short-term: keep exported for compatibility.
- Medium-term: remove `persist()` from the public object. Use a core service:

```python
definition = experiment_service.persist(experiment)
```

- Long-term: decide whether public users should build `Experiment` directly or use a simpler CLI/app facade:

```python
ergon.define(
    benchmark="minif2f",
    worker="react",
    rubric="minif2f",
    model="openai:gpt-4o",
)
```

Decision question:

- Is `Experiment` a public user composition object, or an internal runtime definition draft?

My current leaning:

- Keep `Experiment` public short-term, but make it pure composition with no persistence method.
- If the beginner docs do not need it, do not root-feature it.

### `WorkerSpec`

Current role:

- Config-time descriptor for worker binding.
- Contains `worker_slug`, `name`, and `model`.
- Validates worker slug against `ergon_builtins.registry.WORKERS`.

Where used:

- CLI composition.
- Core launch service.
- Experiment composition and persistence.
- Tests.

Keep in public API?

- Probably not as a beginner concept.

Concerns:

- It is registry/config plumbing.
- It imports builtins registry during validation.
- It exists because live `Worker` requires runtime IDs and cannot be used at config time.

Possible cleanup:

- Move to core composition.
- Keep compatibility import for now.
- Replace public construction with simpler facade args:

```python
worker="researchrubrics-workflow-cli-react"
model="openai:gpt-4o"
```

Decision question:

- Do external users need to build multi-worker assignment graphs manually, or can that be an advanced/core composition feature?

### `PersistedExperimentDefinition`

Current role:

- Handle returned by `Experiment.persist()`.
- Contains `definition_id`, benchmark type, worker/evaluator bindings, counts, created timestamp, and metadata.

Where used:

- CLI benchmark command renders it and uses it to create a run.
- Core run service takes it.
- Core launch service returns it from workflow definition factory.
- Runtime tests instantiate it.

Keep in public API?

- Probably not as student authoring API.

Concerns:

- It is a persistence/launch handle, not an authoring concept.
- Its name overlaps with core `ExperimentDefinition` table rows.

Possible cleanup:

- Move to core composition or core service DTOs.
- Consider rename:
  - `WorkflowDefinitionHandle`
  - `DefinitionHandle`
  - `PersistedDefinition`
- Keep compatibility import until CLI/core imports are migrated.

Decision question:

- Should users ever see persisted definition handles directly, or should they see run IDs/status objects from CLI/app services?

### `BenchmarkDeps`

Current role:

- Onboarding requirements for a benchmark: E2B, extras, optional keys.

Where used:

- Built-in benchmark class vars.
- CLI onboarding profile.
- Benchmark contract tests.

Keep in public API?

- Maybe, but simplify or rehome.

Concerns:

- It duplicates conceptually with `required_packages` and `install_hint`.
- It is not about defining benchmark tasks. It is about onboarding/install/config.
- The `Benchmark` docstring says subclasses must set `onboarding_deps`, but `Benchmark` itself does not define/enforce that class var.

Possible cleanup:

- Merge into a single public metadata object:

```python
requirements = BenchmarkRequirements(
    packages=("datasets", "huggingface_hub"),
    extras=("ergon-builtins[data]",),
    env_keys=("HF_API_KEY",),
    e2b=True,
)
```

- Or keep `BenchmarkDeps` but move to `ergon_core.api.onboarding`.

Decision question:

- Should install/runtime dependencies and onboarding prompts be one concept or two?

### `DependencyError`

Current role:

- Raised when required packages are missing.

Where used:

- Public ABC validation methods.
- Tests may catch or assert dependency behavior.

Keep in public API?

- Maybe.

Concerns:

- If dependency validation moves inward, public users may not need this exception.
- But users might want to catch it around benchmark validation.

Possible cleanup:

- Keep if public `.validate()` methods stay.
- Move if validation becomes core launch-time behavior.

Decision question:

- Is dependency validation part of authoring, or only part of launching/running?

### `CriteriaCheckError`

Current role:

- Domain-level exception criteria can raise from helpers and catch inside `evaluate()` to return a failed `CriterionResult`.

Where used:

- Smoke fixture criteria.
- Built-in criterion tests.

Keep in public API?

- Yes.

Concerns:

- The name uses plural "Criteria" even though a single criterion raises it.

Possible cleanup:

- Keep for compatibility.
- Consider alias:

```python
CriterionCheckError = CriteriaCheckError
```

Decision question:

- Is the plural name worth correcting with an alias, or not worth the churn?

## Boundary Problems To Fix

### Public API Imports Core Persistence

Worst offender:

```text
api/worker.py
   imports core.persistence.context.repository.ContextEventRepository
   imports core.persistence.shared.db.get_session
```

Why it matters:

- A worker author importing `Worker` should not load DB/persistence concerns.
- It creates import-cycle risk.
- It makes the public base class responsible for runtime storage.

Likely fix:

- Move default output extraction to core.
- Let worker runtime call a core helper after `execute()` finishes.

### Public API Imports Core Runtime Protocols

Offender:

```text
api/evaluation_context.py
   imports core.runtime.evaluation.protocols.CriterionRuntime
```

Why it matters:

- Criteria see an internal runtime protocol as a public field.
- It makes the public context harder to document.

Likely fix:

- Make runtime private inside context.
- Expose public methods on context.

### Public API Imports Builtins Registry

Offender:

```text
api/worker_spec.py
   validate_spec() imports ergon_builtins.registry.WORKERS
```

Why it matters:

- `ergon_core.api` should not know about built-ins.
- Registry validation is runtime/composition behavior.

Likely fix:

- Move `WorkerSpec` to core composition.
- Or inject registry validator from core/CLI.

### Public API Imports Core Generation Types

Offender:

```text
api/worker.py
   execute() yields core.generation.ContextPartChunk
```

Why it matters:

- Streaming workers are tightly coupled to Ergon's internal transcript/event model.
- If that is intended, it should be explicitly a public advanced type.

Likely fix:

- Decide whether to publicize a stable streaming event type.
- Or add a simpler `run()` API and keep streaming advanced.

## Consolidation Areas

### Experiment / Definition / Run / Cohort

Current nouns:

```text
Experiment
ExperimentRecord
ExperimentDefinition
PersistedExperimentDefinition
RunRecord
ExperimentCohort
ExperimentCohortStats
```

Possible clean story:

```text
Public:
   Benchmark
   Worker
   Rubric

Application/CLI:
   ExperimentSpec or RunSpec
   RunHandle

Core persistence:
   ExperimentRecord
   ExperimentDefinition
   RunRecord
   ExperimentCohort
```

Open design choice:

- If users think in experiments, keep `Experiment` public, but make it a pure spec.
- If students mostly write benchmarks/workers/rubrics, hide experiment composition behind CLI commands or a service facade.

### Evaluator / Rubric / Evaluation Service

Current nouns:

```text
Evaluator
Rubric
RubricEvaluationService
TaskEvaluationResult
EvaluationSummary
CriterionResultEntry
```

Possible clean story:

```text
Public:
   Criterion
   CriterionResult
   Rubric
   TaskEvaluationResult

Advanced public:
   Evaluator

Core:
   EvaluationRunner
   EvaluationSummary
   CriterionResultEntry
```

Open design choice:

- Keep `Evaluator` root-exported if dynamic task-specific evaluators are important.
- Otherwise feature `Rubric` and let custom evaluators live in an advanced namespace.

### Task / Instance / Workflow Graph

Current nouns:

```text
BenchmarkTask
instance_key
parent_task_slug
dependency_task_slugs
evaluator_binding_keys
ExperimentDefinitionTask
RunTaskExecution
RunGraphNode
```

Possible clean story:

```text
Public beginner:
   Task(slug, description, payload)

Public advanced:
   WorkflowTask(parent, dependencies, evaluator_slots)

Core:
   ExperimentDefinitionTask
   RunTaskExecution
   RunGraphNode
```

Open design choice:

- Do benchmark authors commonly need dependency graphs?
- If yes, keep the fields but document them as advanced.
- If no, split simple task authoring from graph authoring.

## Ergonomic API Options

### Option A: Minimal Authoring Root

Root exports:

```python
from ergon_core.api import (
    Benchmark,
    BenchmarkTask,
    EmptyTaskPayload,
    Worker,
    WorkerContext,
    WorkerOutput,
    Criterion,
    CriterionResult,
    CriterionScoreSpec,
    Rubric,
    TaskEvaluationResult,
    CriteriaCheckError,
)
```

Advanced imports:

```python
from ergon_core.api.advanced import Evaluator, Experiment, WorkerSpec
```

Pros:

- Cleanest beginner story.
- Easy to document.
- Makes runtime/composition concepts visibly advanced.

Cons:

- More migration churn.
- Built-in registry typing and core services need import updates.
- Existing code that imports `Experiment` from public API needs shims.

### Option B: Keep Object-First API, But Purify It

Root exports still include:

```python
Experiment
WorkerSpec
Evaluator
```

But:

- `Experiment.persist()` moves to a service.
- `WorkerSpec.validate_spec()` moves to core composition.
- `Worker.get_output()` no longer reads DB from public base class.
- `EvaluationContext.runtime` becomes private helper-backed capability.

Pros:

- Less disruptive.
- Preserves object-first feel.
- Keeps `Experiment` available for users who naturally want to compose runs in Python.

Cons:

- Beginner docs still need to explain more nouns.
- The top-level API remains larger.
- Harder to communicate what is "normal" vs "advanced".

### Option C: Two Layer Public API

Root beginner API:

```python
Benchmark
Task
Worker
WorkerOutput
Criterion
CriterionResult
Rubric
```

Explicit composition API:

```python
from ergon_core.composition import Experiment, WorkerSpec, persist_experiment
```

or:

```python
from ergon_core.app import define_experiment, run_benchmark
```

Pros:

- Honest separation without hiding useful power.
- CLI and notebook users get a supported high-level entrypoint.
- Students can start with authoring and only learn composition when needed.

Cons:

- Requires new package/module naming decisions.
- Need to avoid having too many "public APIs".

My current recommendation:

- Option C, implemented gradually.
- Keep compatibility re-exports during migration.
- Document `ergon_core.api` as authoring.
- Add a separate high-level app/composition facade for running things.

## Proposed Beginner Docs Shape

### Writing A Benchmark

```python
from ergon_core.api import Benchmark, BenchmarkTask

class MyBenchmark(Benchmark):
    type_slug = "my-benchmark"

    def build_instances(self):
        return {
            "default": [
                BenchmarkTask(
                    task_slug="task-1",
                    instance_key="default",
                    description="Solve this problem.",
                )
            ]
        }
```

Possible future version:

```python
from ergon_core.api import Benchmark, Task

class MyBenchmark(Benchmark):
    type_slug = "my-benchmark"

    def tasks(self):
        yield Task("task-1", "Solve this problem.")
```

### Writing A Worker

Current-ish:

```python
from ergon_core.api import Worker, WorkerContext, BenchmarkTask

class MyWorker(Worker):
    type_slug = "my-worker"

    async def execute(self, task: BenchmarkTask, *, context: WorkerContext):
        ...
```

Possible future beginner version:

```python
from ergon_core.api import Worker, WorkerOutput

class MyWorker(Worker):
    type_slug = "my-worker"

    async def run(self, task, context):
        return WorkerOutput(output="answer")
```

### Writing A Criterion

Current-ish:

```python
from ergon_core.api import Criterion, CriterionResult, EvaluationContext

class MyCriterion(Criterion):
    type_slug = "my-criterion"

    async def evaluate(self, context: EvaluationContext):
        return CriterionResult(
            slug=self.slug,
            name=self.slug,
            score=1.0,
            passed=True,
        )
```

Possible helper version:

```python
return CriterionResult.pass_(self.slug, score=1.0)
```

### Writing A Rubric

```python
from ergon_core.api import Rubric

rubric = Rubric(
    name="default",
    criteria=[MyCriterion(slug="correctness")],
)
```

## Decisions To Make Together

### Public Root Exports

Suggested categories:

```text
Definitely root public:
   Benchmark
   BenchmarkTask or Task
   EmptyTaskPayload
   Worker
   WorkerContext
   WorkerOutput
   Criterion
   CriterionResult
   CriterionScoreSpec
   Rubric
   TaskEvaluationResult
   CriteriaCheckError

Maybe root public:
   EvaluationContext
   Evaluator
   BenchmarkDeps
   DependencyError
   Experiment

Probably not root public long-term:
   WorkerSpec
   PersistedExperimentDefinition
```

### Concept Names

Questions:

- Keep `BenchmarkTask`, or alias it as `Task`?
- Keep `EvaluationContext`, or rename to `CriterionContext`?
- Keep `Evaluator` visible, or make `Rubric` the main public evaluation abstraction?
- Keep `Experiment`, or move composition to a separate facade?
- Rename `PersistedExperimentDefinition` to `WorkflowDefinitionHandle`?
- Rename `RubricEvaluationService` to `EvaluationRunner` or `TaskEvaluationService`?
- Add `CriterionCheckError` alias for `CriteriaCheckError`?

### Simplicity Targets

A clean beginner author should not need to know:

- Inngest,
- database sessions,
- context event persistence,
- run graph node IDs,
- experiment definition row IDs,
- cohort tables,
- telemetry models,
- evaluator binding keys,
- worker binding keys,
- registry validation internals.

They may need to know:

- how to create tasks,
- how a worker receives a task,
- how to return an output,
- how criteria inspect the output,
- how a rubric combines criteria.

## Recommended Refactor Sequence

### Phase 1: Document And Test The Boundary

Add tests that encode:

- `ergon_core.api.worker` must not import DB/session/persistence modules.
- `ergon_core.api.evaluation_context` must not import core runtime protocols directly.
- root exports are intentionally categorized.
- submodule-only public symbols like `CriterionScoreSpec` are either root-exported or documented.

### Phase 2: Remove Runtime Leakage From Public Worker

Move from:

```text
api/worker.py
   ContextEventRepository
   get_session
   AssistantTextPart
```

To:

```text
core/runtime/output_extraction.py
   default_worker_output(context)
```

Then `worker_execute.py` owns the runtime behavior.

### Phase 3: Hide Criterion Runtime Behind Public Context Methods

Move from:

```text
EvaluationContext.runtime: CriterionRuntime | None
```

To:

```text
EvaluationContext.execute_code(...)
EvaluationContext.read_resource(...)
EvaluationContext.read_resource_by_id(...)
```

Internal runtime remains in `core.runtime.evaluation`.

### Phase 4: Move Composition Plumbing

Move:

```text
api/experiment.py -> core/runtime/composition/experiment.py
api/worker_spec.py -> core/runtime/composition/worker_spec.py
api/handles.py -> core/runtime/composition/handles.py
```

Keep compatibility shims temporarily:

```text
api/experiment.py
api/worker_spec.py
api/handles.py
```

But update core and CLI imports to the new home first.

### Phase 5: Add A CLI/Application Facade

Create something like:

```text
core/runtime/services/benchmark_run_facade.py
```

It owns:

- build benchmark from slug,
- attach worker/model/rubric,
- persist definition,
- resolve/create cohort,
- create run,
- emit workflow started event,
- poll run status.

Then `ergon_cli` becomes mostly command parsing and rendering.

### Phase 6: Consolidate Evaluation Naming

Decide:

- root `Rubric` only, or root `Evaluator` too?
- rename internal `RubricEvaluationService`?
- add public helper constructors for result models?
- centralize `CriterionResult` to `EvaluationSummary` conversion.

## Proposed End State

```text
ergon_core.api
   The authoring kit.
   Used by benchmarks, workers, criteria, rubrics, and students.

ergon_core.core.runtime.composition
   Internal composition layer.
   Used by CLI and core services to bind benchmarks, workers, rubrics, assignments.

ergon_core.core.runtime.services
   Application services.
   Used by API routers and CLI facade.

ergon_core.core.persistence
   SQLModel rows and repositories.
   Not imported by public API.

ergon_cli
   Command parsing and display.
   Calls a small core facade, not many low-level services.
```

## Working Recommendation

If we want the cleanest ergonomics for students:

1. Keep the root public API focused on authoring.
2. Keep `Experiment` available for now, but do not teach it first.
3. Move `WorkerSpec` and `PersistedExperimentDefinition` out of the public root over time.
4. Make `Rubric` the public evaluation concept; keep `Evaluator` advanced.
5. Add helper methods/constructors so basic workers and criteria are short to write.
6. Build a separate run/composition facade for CLI and notebook users.

The practical next conversation should decide three things:

1. Is `Experiment` a public composition object or a core definition draft?
2. Is worker authoring streaming-first or output-first?
3. Is `Evaluator` a first-class public concept or an advanced escape hatch behind `Rubric`?
