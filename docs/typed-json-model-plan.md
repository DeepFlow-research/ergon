# Typed JSON Model Plan

## Goal

Improve type safety around `SQLModel` rows that currently store structured JSON as raw `dict`/`list`, without making persistence awkward or forcing application logic to keep using dictionary access.

The core problem is:

- the database layer needs JSON-serializable values
- the application layer wants strongly typed objects
- some current call sites consume raw JSON directly

## Short Answer

Adding `after` validators to the SQL models can improve **runtime correctness**, but by itself it will usually **not** give much better static type safety if the field annotation stays `dict`.

If the field is still declared as:

```python
ground_truth_rubric: dict
```

then most callers and type checkers will still treat it as a `dict`, even if a validator has already checked that the data matches some richer shape.

## Recommendation

Use a **typed facade over raw persistence**:

1. Keep JSON columns stored as raw JSON-compatible shapes in `SQLModel`.
2. Add typed parser/accessor methods for important JSON-backed fields.
3. Gradually migrate application code to consume those typed helpers or typed DTOs instead of raw `dict`s.
4. Use validators as guards and normalization tools, not as the only typing mechanism.

This is already the pattern used for `task_tree`, where storage is raw JSON but application code parses it into `TaskTreeNode`.

## Why Validators Alone Are Not Enough

An `@model_validator(mode="after")` is useful for:

- failing fast on invalid persisted data
- normalizing input
- deriving cached/computed fields
- enforcing invariants

But it does **not** automatically change what downstream code sees in the type system.

For example, this improves runtime safety:

```python
class Experiment(SQLModel, table=True):
    ground_truth_rubric: dict = Field(sa_column=Column(JSON))

    @model_validator(mode="after")
    def validate_ground_truth_rubric(self) -> "Experiment":
        ResearchRubricsRubric.model_validate(self.ground_truth_rubric)
        return self
```

However, downstream code still sees:

```python
experiment.ground_truth_rubric  # typed as dict
```

So consumers still tend to write `dict.get(...)`, string-key lookups, and shape assumptions.

## Better Pattern: Typed Accessors

Keep the persisted field raw, but expose a typed API on the model.

Example:

```python
from typing import cast

from h_arcane.benchmarks.enums import BenchmarkName
from h_arcane.benchmarks.gdpeval.rubric import StagedRubric
from h_arcane.benchmarks.researchrubrics.rubric import ResearchRubricsRubric


class Experiment(SQLModel, table=True):
    benchmark_name: BenchmarkName
    ground_truth_rubric: dict = Field(sa_column=Column(JSON))

    def parsed_ground_truth_rubric(self) -> ResearchRubricsRubric | StagedRubric:
        if self.benchmark_name == BenchmarkName.RESEARCHRUBRICS:
            return ResearchRubricsRubric.model_validate(self.ground_truth_rubric)
        if self.benchmark_name == BenchmarkName.GDPEVAL:
            return StagedRubric.model_validate(self.ground_truth_rubric)
        raise ValueError(f"Unsupported benchmark_name: {self.benchmark_name}")
```

That way callers can use:

```python
rubric = experiment.parsed_ground_truth_rubric()
```

and now the application boundary is explicitly typed.

## Are Validator / Accessor Methods Bound To The Data Model Class?

Yes, they usually are if you define them as instance methods on the model class.

### Validator

A validator is bound to the class as part of Pydantic model validation. It runs when the model is created or validated.

Example:

```python
from pydantic import model_validator


class TaskEvaluator(SQLModel, table=True):
    evaluator_type: str
    evaluator_config: dict = Field(sa_column=Column(JSON))

    @model_validator(mode="after")
    def validate_evaluator_config(self) -> "TaskEvaluator":
        deserialize_rubric(self.evaluator_type, self.evaluator_config)
        return self
```

Notes:

- this is bound to the class definition
- it runs during model validation
- it is good for correctness
- it does not make `evaluator_config` statically typed beyond `dict`

### Accessor Method

An accessor is just a normal instance method or property on the model class that returns a typed object.

Example:

```python
class TaskEvaluator(SQLModel, table=True):
    evaluator_type: str
    evaluator_config: dict = Field(sa_column=Column(JSON))

    def parsed_evaluator(self) -> AnyRubric:
        return deserialize_rubric(self.evaluator_type, self.evaluator_config)
```

Notes:

- this is also bound to the class as an instance method
- it runs only when called
- it gives callers a typed object they can program against
- it fits the persistence/application split better

## Validator vs Accessor

### Validator

Pros:

- catches invalid data early
- centralizes validation
- can normalize data once at model construction time

Cons:

- does not fix the field's static type if annotation stays `dict`
- can make row loading fail for old/bad DB data
- can create hidden coupling between persistence and higher-level domain types

### Accessor

Pros:

- makes the typed boundary explicit
- preserves raw storage shape
- gives better ergonomics for consumers
- easier to migrate incrementally

Cons:

- parsing happens when called unless you cache it
- callers must choose to use the accessor instead of the raw field

## Best Combined Approach

The strongest practical pattern is:

- store raw JSON in the SQL row
- optionally validate it at model construction or at write boundaries
- expose typed accessors for application logic
- prefer passing typed objects or typed DTOs into business logic instead of full row models

In other words:

- validators are good guards
- accessors are the better application-facing API

## Suggested Phased Refactor

### Phase 1: Add Typed Accessors For High-Value Fields

Start with fields that already behave like structured models:

- `Experiment.task_tree -> TaskTreeNode`
- `Experiment.ground_truth_rubric -> typed rubric/config`
- `Run.execution_result -> ExecutionResult`
- `TaskEvaluator.evaluator_config -> AnyRubric`
- `TaskEvaluationResult.criterion_results -> list[CriterionResult]`
- `Action.error -> ExecutionError`
- `CriterionResult.error -> ExecutionError`

Some of these already exist in partial form.

### Phase 2: Migrate Consumers

Change application code from patterns like:

```python
experiment.ground_truth_rubric.get("criteria", [])
```

to patterns like:

```python
rubric = experiment.parsed_ground_truth_rubric()
criteria = rubric.rubric_criteria
```

This is where most type-safety gains show up.

### Phase 3: Add Guard Validators Selectively

Add validators only where invalid persisted state should clearly fail fast.

Good candidates:

- `TaskEvaluator.evaluator_config`
- `Run.execution_result`
- `Experiment.task_tree`

Be cautious with fields that are intentionally flexible or partially schema-less.

### Phase 4: Introduce DTOs Where Functions Should Not Accept Raw Rows

If a function really needs typed application data, pass that typed data directly rather than a whole ORM row.

Example:

```python
class StakeholderInput(BaseModel):
    task_prompt: str
    rubric: ResearchRubricsRubric
```

Then:

```python
stakeholder = RubricAwareStakeholder(
    StakeholderInput(
        task_prompt=experiment.task_description,
        rubric=experiment.parsed_ground_truth_rubric(),
    )
)
```

This is often better than making every consumer depend on `Experiment`.

## What I Would Not Do First

I would not start by changing JSON columns so that the ORM field itself stores a live Pydantic model instance in memory while serializing transparently to Postgres, unless you are ready for a deeper SQLAlchemy customization.

That is possible with a custom `TypeDecorator`, but it is a larger ORM decision and not necessary to get most of the type-safety benefits.

## Proposed Initial Targets In This Codebase

### `Experiment`

Add:

- `parsed_task_tree() -> TaskTreeNode | None`
- `parsed_ground_truth_rubric() -> ...`

### `Run`

Add:

- `parsed_execution_result() -> ExecutionResult | None`

### `TaskEvaluator`

Add:

- `parsed_evaluator() -> AnyRubric`

### `TaskEvaluationResult`

Add:

- `parsed_criterion_results() -> list[CriterionResult]`

## Opinionated Recommendation

If the goal is "application logic should not have to treat structured JSON as dictionaries," the best next step is:

1. add typed accessor methods
2. migrate call sites to use them
3. add validators selectively for fail-fast protection

That gets most of the benefit with low migration risk and keeps persistence concerns separate from application concerns.

## Example Final Direction

This is the direction I would aim for:

```python
class Run(SQLModel, table=True):
    execution_result: dict | None = Field(default=None, sa_column=Column(JSON))

    def parsed_execution_result(self) -> ExecutionResult | None:
        if self.execution_result is None:
            return None
        return ExecutionResult.model_validate(self.execution_result)
```

Then callers use:

```python
result = run.parsed_execution_result()
if result and result.success:
    ...
```

This keeps the row persistence-friendly while giving the rest of the codebase a typed API.

## Concrete Class Pattern

Use the same structure for every JSON-backed field that deserves a typed API:

```python
class Run(SQLModel, table=True):
    execution_result: dict | None = Field(default=None, sa_column=Column(JSON))

    def parsed_execution_result(self) -> ExecutionResult | None:
        return self.__class__._parse_execution_result(self.execution_result)

    @classmethod
    def _parse_execution_result(cls, data: dict | None) -> ExecutionResult | None:
        if data is None:
            return None
        return ExecutionResult.model_validate(data)
```

Why this pattern:

- `parsed_*()` is the public application-facing API
- `_parse_*()` is the reusable parsing boundary
- parsing logic stays close to the field it belongs to
- callers never need to know how the raw JSON is interpreted

For fields that depend on another column, pass both values into the private parser:

```python
class Experiment(SQLModel, table=True):
    benchmark_name: BenchmarkName = Field(index=True)
    ground_truth_rubric: dict = Field(sa_column=Column(JSON))

    def parsed_ground_truth_rubric(self) -> AnyRubric:
        return self.__class__._parse_ground_truth_rubric(
            self.benchmark_name,
            self.ground_truth_rubric,
        )

    @classmethod
    def _parse_ground_truth_rubric(
        cls,
        benchmark_name: BenchmarkName,
        data: dict,
    ) -> AnyRubric:
        ...
```

## Scope

This concrete plan applies to:

- JSON-backed `dict` fields
- JSON-backed `list[...]` fields that really represent typed records or UUIDs
- helper/convenience methods already doing parsing informally

It does **not** try to wrap every scalar field. Plain columns like `str`, `UUID`, `datetime`, `float`, and enums should stay as ordinary fields with no parsing layer.

## Field-By-Field Plan

Below is the recommended implementation plan for every structured attribute in `models.py`.

### `ExecutionError`

This is already the typed model for error payloads. No persistence wrapper is needed here.

Recommendation:

- keep as-is
- continue using `create_execution_error(...)`
- treat this as the canonical parser target for `Action.error` and `CriterionResult.error`

Add:

- no new parser needed on `ExecutionError`

### `Experiment.ground_truth_rubric`

Current shape:

- stored as `dict`
- meaning depends on `benchmark_name`

Recommendation:

- add a public accessor
- add a private class parser that dispatches on `benchmark_name`
- this should become the main way app code consumes rubrics/configs from the row

Add:

- `parsed_ground_truth_rubric(self) -> AnyRubric`
- `_parse_ground_truth_rubric(cls, benchmark_name: BenchmarkName, data: dict) -> AnyRubric`

Implementation note:

- use benchmark dispatch rather than raw `dict.get(...)`
- for unsupported/custom benchmarks, either raise clearly or introduce a typed fallback model later

Migration targets:

- `benchmarks/researchrubrics/stakeholder.py`
- any benchmark factories/loaders currently using `ground_truth_rubric.get(...)`

### `Experiment.benchmark_specific_data`

Current shape:

- stored as `dict`
- benchmark-specific and currently fairly loose

Recommendation:

- add a parser/accessor only if you define benchmark-specific typed schemas
- otherwise keep raw for now

Add now:

- `benchmark_specific_data_for(self) -> dict`

Add later when schemas exist:

- `parsed_benchmark_specific_data(self) -> BenchmarkSpecificDataModel`
- `_parse_benchmark_specific_data(cls, benchmark_name: BenchmarkName, data: dict) -> ...`

Implementation note:

- do not force a typed parser yet if the schema is still unstable
- treat this as a second-wave migration after `ground_truth_rubric`

### `Experiment.task_tree`

Current shape:

- stored as `dict`
- already has a typed parser function in `task/schema.py`

Recommendation:

- add a model-bound accessor that delegates to the existing parser
- add a private class parser on `Experiment` for consistency, even if it just wraps `parse_task_tree`

Add:

- `parsed_task_tree(self) -> TaskTreeNode | None`
- `_parse_task_tree(cls, data: dict | None) -> TaskTreeNode | None`

Implementation note:

- keep `parse_task_tree(...)` as the underlying implementation initially
- `Experiment.parsed_task_tree()` becomes the row-local entry point

Migration targets:

- replace direct `parse_task_tree(experiment.task_tree)` with `experiment.parsed_task_tree()`

### `Run.output_resource_ids`

Current shape:

- stored as `list[str]`
- semantically represents resource UUIDs

Recommendation:

- add typed UUID conversion helpers
- keep raw field for persistence

Add:

- `parsed_output_resource_ids(self) -> list[UUID]`
- `_parse_output_resource_ids(cls, data: list[str]) -> list[UUID]`

Implementation note:

- this is useful if application code wants typed UUIDs instead of strings
- if most call sites immediately re-query resources, this accessor is optional but still consistent

### `Run.benchmark_specific_results`

Current shape:

- stored as `dict`
- currently mixed use: workflow evaluation details plus ad hoc keys like `cli_request_id` and `agent_mapping`

Recommendation:

- do not force a single typed parser yet
- split this conceptually into named typed accessors for known sub-keys

Add now:

- `benchmark_specific_results_for(self) -> dict`
- `cli_request_id(self) -> str | None`
- `agent_mapping(self) -> dict[str, str] | None`

Potential later additions:

- `parsed_benchmark_specific_results(self) -> BenchmarkResultsModel`
- `_parse_benchmark_specific_results(cls, benchmark_name: BenchmarkName, data: dict) -> ...`

Implementation note:

- this field is too overloaded today for one clean parser
- the plan should be to carve out typed sub-accessors before introducing a single model

### `Run.execution_result`

Current shape:

- stored as `dict | None`
- already deserialized ad hoc with `ExecutionResult.model_validate(...)`

Recommendation:

- add an accessor and private parser immediately
- this is one of the cleanest, highest-value targets

Add:

- `parsed_execution_result(self) -> ExecutionResult | None`
- `_parse_execution_result(cls, data: dict | None) -> ExecutionResult | None`

Migration targets:

- `core/runner.py`
- any workflow completion/failure code that reconstructs this payload

Optional validator:

- yes, strong candidate for an `after` validator if you want fail-fast on invalid stored state

### `Action.error`

Current shape:

- stored as `dict | None`
- already has `get_error()`

Recommendation:

- keep the existing public helper
- optionally rename for consistency, or leave as-is and standardize around it
- add a private parser to align with the pattern

Add:

- keep `get_error(self) -> ExecutionError | None`
- add `_parse_error(cls, data: dict | None) -> ExecutionError | None`

Optional refinement:

- optionally add `parsed_error()` as an alias if you want all accessors to share one naming convention

### `ResourceRecord.source_resource_ids`

Current shape:

- stored as `list[str]`
- semantically represents resource UUIDs

Recommendation:

- add UUID parsing helpers

Add:

- `parsed_source_resource_ids(self) -> list[UUID]`
- `_parse_source_resource_ids(cls, data: list[str]) -> list[UUID]`

Implementation note:

- useful when lineage logic wants typed IDs
- low risk, easy to implement

### `AgentConfig.tools`

Current shape:

- stored as `list[str]`
- semantically already a display/logging representation, not a richer object graph

Recommendation:

- keep raw
- no parser needed

Reason:

- the stored values are tool names, not reconstructable live tool objects
- trying to type this more strongly adds little value

Possible accessor:

- `tool_names(self) -> list[str]`

but this is optional and mostly stylistic

### `TaskExecution.output_resource_ids`

Current shape:

- stored as `list[str]`
- semantically resource UUIDs

Recommendation:

- add UUID parsing helpers

Add:

- `parsed_output_resource_ids(self) -> list[UUID]`
- `_parse_output_resource_ids(cls, data: list[str]) -> list[UUID]`

### `TaskExecution.evaluation_details`

Current shape:

- stored as `dict`
- semantics currently unclear / likely benchmark- or evaluator-specific

Recommendation:

- defer a single parser unless the schema is stabilized
- start with keyed accessors for known subshapes if they emerge

Add now:

- `evaluation_details_for(self) -> dict`

Add later:

- `parsed_evaluation_details(self) -> TaskExecutionEvaluationDetails`
- `_parse_evaluation_details(cls, data: dict) -> TaskExecutionEvaluationDetails`

### `TaskStateEvent.event_metadata`

Current shape:

- stored as `dict`
- depends on `event_type` and trigger source

Recommendation:

- do not add a general typed parser yet
- if event metadata becomes structured, parse by `event_type`

Add now:

- `metadata_for(self) -> dict`

Add later:

- `parsed_event_metadata(self) -> EventMetadataModel`
- `_parse_event_metadata(cls, event_type: str, data: dict) -> ...`

Reason:

- this field is event-log metadata and is likely to remain extensible

### `TaskEvaluator.evaluator_config`

Current shape:

- stored as `dict`
- meaning determined by `evaluator_type`
- already deserialized externally with `deserialize_rubric(...)`

Recommendation:

- add accessor + private parser immediately
- strong candidate for a validator

Add:

- `parsed_evaluator(self) -> AnyRubric`
- `_parse_evaluator(cls, evaluator_type: str, data: dict) -> AnyRubric`

Optional validator:

- `validate_evaluator_config()` calling `_parse_evaluator(...)`

Migration targets:

- `check_evaluators.py`
- any evaluator creation/inspection code

### `CriterionResult.error`

Current shape:

- stored as `dict | None`
- already has `get_error()`

Recommendation:

- same treatment as `Action.error`

Add:

- keep `get_error(self) -> ExecutionError | None`
- add `_parse_error(cls, data: dict | None) -> ExecutionError | None`

### `CriterionResult.evaluated_action_ids`

Current shape:

- stored as `list[str]`
- semantically action UUIDs

Recommendation:

- add UUID parsing helpers

Add:

- `parsed_evaluated_action_ids(self) -> list[UUID]`
- `_parse_evaluated_action_ids(cls, data: list[str]) -> list[UUID]`

### `CriterionResult.evaluated_resource_ids`

Current shape:

- stored as `list[str]`
- semantically resource UUIDs

Recommendation:

- add UUID parsing helpers

Add:

- `parsed_evaluated_resource_ids(self) -> list[UUID]`
- `_parse_evaluated_resource_ids(cls, data: list[str]) -> list[UUID]`

### `TaskEvaluationResult.criterion_results`

Current shape:

- stored as `list[dict]`
- each item is a serialized `CriterionResult`

Recommendation:

- add accessor + private parser immediately
- this is a strong typed boundary candidate

Add:

- `parsed_criterion_results(self) -> list[CriterionResult]`
- `_parse_criterion_results(cls, data: list[dict]) -> list[CriterionResult]`

Implementation note:

- use `CriterionResult.model_validate(...)` per entry
- consider a future `TypeAdapter(list[CriterionResult])` if desired

## Standard Helper Types

For the first implementation pass, define these parse targets as the canonical typed representations:

- `Experiment.ground_truth_rubric -> AnyRubric`
- `Experiment.task_tree -> TaskTreeNode | None`
- `Run.execution_result -> ExecutionResult | None`
- `Action.error -> ExecutionError | None`
- `ResourceRecord.source_resource_ids -> list[UUID]`
- `TaskEvaluator.evaluator_config -> AnyRubric`
- `CriterionResult.error -> ExecutionError | None`
- `CriterionResult.evaluated_action_ids -> list[UUID]`
- `CriterionResult.evaluated_resource_ids -> list[UUID]`
- `TaskEvaluationResult.criterion_results -> list[CriterionResult]`

These are the fields that already have enough semantic structure to justify typing immediately.

## Recommended Naming Rules

To keep the API consistent across models:

- use `parsed_<field_name>()` for public typed accessors
- use `_parse_<field_name>(...)` for private class parser helpers
- use `get_error()` only where preserving existing API matters
- use `<field_name>_for()` only for intentionally raw passthrough helpers

Examples:

- `parsed_task_tree()`
- `_parse_task_tree(...)`
- `parsed_execution_result()`
- `_parse_execution_result(...)`
- `benchmark_specific_results_for()`

## Validators: Exact Recommendation

If you want validator coverage, I would apply it only to fields whose schema is already stable and important:

Add validators now:

- `Experiment.task_tree`
- `Run.execution_result`
- `TaskEvaluator.evaluator_config`

Maybe add later:

- `Experiment.ground_truth_rubric`

Do not add validators yet:

- `Experiment.benchmark_specific_data`
- `Run.benchmark_specific_results`
- `TaskExecution.evaluation_details`
- `TaskStateEvent.event_metadata`

Reason:

- the first group has clear, stable parser targets
- the second group is still too heterogeneous

## Implementation Order

If implementing this as a concrete refactor, I would do it in this order:

1. Add the parser/accessor pair for `Experiment.task_tree`, `Run.execution_result`, and `TaskEvaluator.evaluator_config`.
2. Migrate current call sites to use the accessors.
3. Add parser/accessor pairs for `TaskEvaluationResult.criterion_results`, `Action.error`, and `CriterionResult.error`.
4. Add UUID list accessors for resource/action ID fields.
5. Only then start carving typed sub-accessors out of `benchmark_specific_results`, `benchmark_specific_data`, `evaluation_details`, and `event_metadata`.

## Concrete Deliverable For `models.py`

If you implement this plan fully, `models.py` should end up with:

- one public typed accessor for every structured field that has a stable schema
- one private class parser per accessor
- selective validators only on the most stable/high-value fields
- no attempt to force schema-less metadata blobs into premature rigid models

That gives you a consistent rule:

- rows store JSON-friendly primitives
- model methods expose typed views
- business logic consumes typed views, not raw JSON
