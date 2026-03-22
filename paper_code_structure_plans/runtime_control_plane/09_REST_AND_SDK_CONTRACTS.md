# REST And SDK Contracts

## Purpose

This document ties together the runtime-control-plane design as concrete contract shapes:

- public Python SDK
- runtime submission payloads
- likely REST endpoints
- visibility boundaries between public and internal types

The goal is not to freeze every exact field now, but to make the system concrete enough that implementation can start cleanly.

## Public SDK Surface

The main public authoring surface should stay intentionally small.

### Public constructible

- `EvalSpec`
- `ModelTarget`
- `LaunchSpec`
- `DispatchSpec`
- `ArcaneClient`

### Public inspectable

- `SubmittedRun`
- `RunSnapshot`
- `ExecutionResult`

### Internal-first

- `PolicyVersion`
- `RolloutGroup`
- `TrainingWindow`
- `TrainingJob`
- `ServingDeployment`
- provider backend resource handles and statuses

## Python SDK Shape

### Core public call

```python
class ArcaneClient:
    def __init__(self, target: str = "local"): ...

    async def evaluate(
        self,
        eval_spec: EvalSpec,
        *,
        model: ModelTarget,
        dispatch: DispatchSpec | None = None,
    ) -> SubmittedRun:
        ...

    async def get_run(self, run_id: UUID) -> RunSnapshot:
        ...

    async def wait(
        self,
        run_id: UUID,
        *,
        timeout_seconds: float | None = None,
    ) -> ExecutionResult:
        ...
```

### Future control-plane methods

These are internal-first or advanced for now, but likely belong in the same client eventually:

```python
async def create_rollout_group(...)
async def set_rollout_group_state(...)
async def seal_training_window(...)
async def launch_training(...)
async def register_policy_version(...)
async def promote_policy_version(...)
```

## Core Submission Types

### `EvalSpec`

```python
class EvalSpec(BaseModel):
    benchmark: str
    split: str | None = None
    workflow: str | None = None
    experiment_ids: list[UUID] = Field(default_factory=list)
    task_ids: list[str] = Field(default_factory=list)
    limit: int | None = None
    cohort_name: str | None = None
    max_questions: int = 10
    timeout_seconds: float | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
```

### `ModelTarget`

```python
class ModelTarget(BaseModel):
    kind: Literal["provider", "endpoint", "managed"]
    model_name: str
    version: str | None = None
    provider: str | None = None
    endpoint: str | None = None
    generation_config: dict[str, Any] = Field(default_factory=dict)
    launch: LaunchSpec | None = None
```

### `DispatchSpec`

```python
class DispatchSpec(BaseModel):
    max_concurrent_tasks: int = 10
    metadata: dict[str, Any] = Field(default_factory=dict)
```

### `EvaluationSubmissionRequest`

```python
class EvaluationSubmissionRequest(BaseModel):
    eval: EvalSpec
    model: ModelTarget
    dispatch: DispatchSpec = Field(default_factory=DispatchSpec)
```

## Suggested REST Endpoints

### Evaluation submission

`POST /api/evals`

Request:

```json
{
  "eval": {
    "benchmark": "minif2f",
    "split": "valid",
    "limit": 100,
    "cohort_name": "qwen-local"
  },
  "model": {
    "kind": "endpoint",
    "model_name": "qwen-32b",
    "version": "local-dev",
    "endpoint": "http://localhost:8000"
  },
  "dispatch": {
    "max_concurrent_tasks": 10
  }
}
```

Response:

```json
{
  "run_id": "uuid",
  "experiment_id": "uuid-or-null",
  "status": "submitted",
  "target": "local"
}
```

### Run lookup

`GET /api/runs/{run_id}`

Returns a `RunSnapshot`.

### Run wait/poll

Initially, this can simply be:

- repeated `GET /api/runs/{run_id}`

with the Python SDK implementing polling in `wait(...)`.

### Future control-plane endpoints

Likely later:

- `POST /api/rollout-groups`
- `POST /api/rollout-groups/{id}/state`
- `POST /api/training-windows/seal`
- `POST /api/training-jobs`
- `POST /api/policy-versions/{version}/promote`

These can remain internal or advanced until the control-plane surface is ready.

## Submission Semantics

The key contract is:

- the user submits `EvalSpec + ModelTarget + DispatchSpec`
- the runtime/control plane resolves the model target
- the runtime persists model provenance
- the runtime creates whatever internal control-plane state is needed

This means the public submission contract stays simple even if the internal system evolves into rollout groups, policy versions, and training windows.

## Model Provenance Requirements

Every submitted run should persist enough information to answer:

- what model was intended
- what actual endpoint/provider was used
- what version was used
- what generation config was active

This should be reflected in run metadata and later trace data.

The API should make it impossible to silently lose model provenance.

## Visibility Boundary In Practice

This contract doc intentionally does **not** expose `PolicyVersion`, `RolloutGroup`, or `TrainingWindow` as everyday public authoring types.

Why:

- they are orchestration lifecycle objects
- they are more likely to evolve
- most users should not need them to run evaluations

They may become public read models later, but they should not be the main SDK entrypoint now.

## Final Position

The practical contract set for implementation should be:

- small public SDK surface
- explicit serialized submission request
- stable REST entrypoint for evaluation
- strong model provenance
- internal control-plane expansion behind the submission boundary

That gives Arcane room to grow without forcing the first user-facing API to become orchestration-heavy too early.
