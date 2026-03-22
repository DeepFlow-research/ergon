# Public API Napkin Sketch

## Design Goal

The API should optimize for the most common user question:

**run this evaluation against this model target**

That means:

- `EvalSpec` should be stable
- `ModelTarget` should be swappable
- deployment details should only appear when necessary
- serious execution should go through the Arcane runtime

## Core Public Types

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

This is the stable part.

### `ModelTarget`

```python
class ModelTarget(BaseModel):
    kind: Literal["provider", "endpoint", "managed"]
    model_name: str
    version: str | None = None
    provider: str | None = None
    endpoint: str | None = None
    generation_config: dict[str, Any] = Field(default_factory=dict)
    launch: "LaunchSpec | None" = None
```

This is the swappable part.

### `LaunchSpec`

```python
class LaunchSpec(BaseModel):
    backend: Literal["local", "compose", "k8s", "slurm", "skypilot"]
    accelerator: str | None = None
    replicas: int = 1
    image: str | None = None
    launcher_config: dict[str, Any] = Field(default_factory=dict)
```

Only required for `managed` model targets.

### `TrainerSpec`

```python
class TrainerSpec(BaseModel):
    backend: str
    config: dict[str, Any] = Field(default_factory=dict)
```

This is intentionally small here. The important thing is that the control plane can refer to a trainer backend without baking backend-specific fields into the core evaluation surface.

### `DispatchSpec`

```python
class DispatchSpec(BaseModel):
    max_concurrent_tasks: int = 10
    metadata: dict[str, Any] = Field(default_factory=dict)
```

This should stay intentionally small for now.

## Primary Client

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

## Submission Shape

The runtime submission boundary should be explicit.

```python
class EvaluationSubmissionRequest(BaseModel):
    eval: EvalSpec
    model: ModelTarget
    dispatch: DispatchSpec = Field(default_factory=DispatchSpec)
```

The runtime turns this into:

- persisted run metadata
- model provenance
- rollout or execution state
- control-plane objects as needed

## Example Usage

### Cloud model

```python
client = ArcaneClient(target="local")

run = await client.evaluate(
    EvalSpec(
        benchmark="minif2f",
        split="valid",
        limit=100,
        cohort_name="gpt4o-smoke",
    ),
    model=ModelTarget(
        kind="provider",
        provider="openai",
        model_name="gpt-4o",
    ),
)
```

### Existing local endpoint

```python
run = await client.evaluate(
    EvalSpec(
        benchmark="minif2f",
        split="valid",
        limit=100,
        cohort_name="qwen-local",
    ),
    model=ModelTarget(
        kind="endpoint",
        model_name="qwen-32b",
        version="local-dev",
        endpoint="http://localhost:8000",
    ),
)
```

### Managed local launch

```python
run = await client.evaluate(
    EvalSpec(
        benchmark="minif2f",
        split="valid",
        limit=100,
        cohort_name="qwen-managed",
    ),
    model=ModelTarget(
        kind="managed",
        model_name="qwen-32b",
        version="candidate-17",
        launch=LaunchSpec(
            backend="slurm",
            accelerator="a100:2",
            launcher_config={"partition": "gpu"},
        ),
    ),
)
```

## Control-Plane Types

These are not necessarily part of the simplest public SDK at first, but Arcane should likely have stable models for them internally and perhaps later publicly.

### `PolicyVersion`

```python
class PolicyVersion(BaseModel):
    policy_id: str
    version: str
    artifact_uri: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
```

### `RolloutGroup`

```python
class RolloutGroupState(str, Enum):
    RUNNING = "running"
    PAUSED = "paused"
    DRAINING = "draining"
    STOPPED = "stopped"


class RolloutGroup(BaseModel):
    id: UUID
    eval: EvalSpec
    policy_version: str
    state: RolloutGroupState
    max_concurrency: int
```

### `TrainingWindow`

```python
class TrainingWindow(BaseModel):
    id: UUID
    source_policy_version: str
    status: Literal["open", "sealed", "training", "consumed"]
    metadata: dict[str, Any] = Field(default_factory=dict)
```

## Provider Backend Sketch

These types are likely internal-first, but the overall API sketch should make room for them explicitly.

### `ClusterSpec`

```python
class ClusterSpec(BaseModel):
    accelerator: str | None = None
    node_count: int = 1
    image: str | None = None
    config: dict[str, Any] = Field(default_factory=dict)
```

### `ServiceSpec`

```python
class ServiceSpec(BaseModel):
    kind: str
    image: str | None = None
    command: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)
    config: dict[str, Any] = Field(default_factory=dict)
```

### `JobSpec`

```python
class JobSpec(BaseModel):
    kind: str
    image: str | None = None
    command: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)
    config: dict[str, Any] = Field(default_factory=dict)
```

### `LaunchProvider`

```python
class LaunchProvider(Protocol):
    async def create_cluster(self, spec: ClusterSpec) -> ClusterHandle:
        ...

    async def get_cluster(self, cluster_id: str) -> ClusterStatus:
        ...

    async def delete_cluster(self, cluster_id: str) -> None:
        ...

    async def create_service(self, spec: ServiceSpec) -> ServiceHandle:
        ...

    async def get_service(self, service_id: str) -> ServiceStatus:
        ...

    async def delete_service(self, service_id: str) -> None:
        ...

    async def submit_job(self, spec: JobSpec) -> JobHandle:
        ...

    async def get_job(self, job_id: str) -> JobStatus:
        ...

    async def stop_job(self, job_id: str) -> None:
        ...
```

Arcane should own the decision to ask for a service or job. The provider backend should own the mechanics of making that real.

## Minimal REST Shape

If mirrored via REST, the shape should stay close to the Python SDK.

### Submit evaluation

`POST /api/evals`

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

### Get run

`GET /api/runs/{run_id}`

### Wait for run

Could be:

- `GET /api/runs/{run_id}`
- or a convenience long-poll / stream endpoint later

## What This API Intentionally Avoids

This sketch intentionally avoids:

- embedding live worker objects in task definitions
- making the user think in scheduler primitives first
- exposing rollout worker management as the first user interaction
- binding the API to Compose-specific assumptions

That complexity belongs below the user’s default evaluation flow.

## Visibility And Type Boundaries

It is worth being explicit now about which of these proposed types should be public versus internal.

If this is not specified early, the redesign risks either:

- leaking too much control-plane machinery into the SDK surface, or
- depending on internal shapes that users accidentally start treating as public contracts

The goal should be to keep the public surface small and ergonomic while still letting the runtime own richer internal state.

### Public constructible SDK types

These are the types users should be expected to construct directly in normal code:

- `EvalSpec`
- `ModelTarget`
- `LaunchSpec`
- `DispatchSpec`
- `ArcaneClient`

Why these are public:

- they correspond to the main authoring and submission task
- they express user intent directly
- they are the natural stable surface for evaluation ergonomics

### Public inspectable response/view types

These are types users may receive from Arcane or inspect through the SDK/API, but should not necessarily be expected to construct by hand:

- `SubmittedRun`
- `RunSnapshot`
- `ExecutionResult`
- future `CohortSummary` / `ExperimentSummary`-style views
- possibly later read-only views over `PolicyVersion` / `TrainingJob`

Why these are public:

- users need to inspect run state and outcomes
- they are part of the read path of the system
- they support debugging, dashboards, and programmatic monitoring

### Internal control-plane types

These should be treated as internal-first, even if they may eventually become inspectable or partially exposed:

- `PolicyVersion`
- `RolloutGroup`
- `RolloutGroupState`
- `TrainingWindow`
- `TrainingJob`
- `ServingDeployment`
- `LaunchProvider`
- `ClusterSpec`
- `JobSpec`
- `ServiceSpec`

Why these should be internal-first:

- they represent Arcane’s orchestration and lifecycle model
- they are likely to change more as the RL/control-plane design matures
- exposing them too early would freeze the wrong abstractions

This is especially true for `PolicyVersion`. Most users do not need to construct policy-version objects directly in order to run evaluations. What they need is to select a model through `ModelTarget`. Internally, Arcane may resolve that to a concrete immutable policy version, but that is a control-plane concern rather than part of the everyday SDK authoring surface.

### Public later, possibly read-only

Some internal control-plane types may later become public in a read-only or inspectable form if the control plane becomes a more explicit product surface.

The most likely candidates are:

- `PolicyVersion`
- `RolloutGroup`
- `TrainingJob`

But even then, the likely right model is:

- public to inspect
- not necessarily public to construct

That distinction matters. A user may need to query a rollout group or policy version, but that does not mean they should be building those objects manually in normal SDK usage.

### Rule of thumb

The simplest rule is:

- if users need to write it by hand in day-to-day evaluation code, it should probably be public
- if Arcane mostly creates and manages it as part of orchestration, it should probably be internal or read-only public

By that rule:

- `ModelTarget` is public
- `EvalSpec` is public
- `PolicyVersion` is internal-first
- `RolloutGroup` is internal-first
- `TrainingWindow` is internal-first

### Recommended package split

This distinction should eventually be reflected in module layout.

For example:

```text
h_arcane/sdk/
  evals.py
  models.py
  client.py

h_arcane/views/
  runs.py
  cohorts.py

h_arcane/core/control_plane/
  policy_versions.py
  rollout_groups.py
  training_windows.py
  serving_deployments.py
```

This is not a final required structure, but it illustrates the intended visibility boundary:

- SDK modules for authoring and submission
- view modules for inspection/read models
- control-plane modules for internal lifecycle state

### Final position

The public SDK should stay narrow.

The main public authoring surface should be centered on:

- `EvalSpec`
- `ModelTarget`
- `LaunchSpec`
- `DispatchSpec`
- `ArcaneClient`

Control-plane resource types should remain internal-first until there is a clear reason to expose them as part of a stable user-facing orchestration API.

## Final Position

The API should feel like:

- choose the eval
- choose the model
- optionally attach launch details
- submit to Arcane

That is the cleanest path that still leaves room for larger async RL systems later.
