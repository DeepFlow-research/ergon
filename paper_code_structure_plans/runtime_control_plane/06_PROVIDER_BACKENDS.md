# Provider Backends

## Purpose

This document specifies the role of provider backends in the runtime-control-plane architecture.

The core position is:

- Arcane owns dispatch intent and lifecycle
- provider backends own the realization of infrastructure resources

This lets Arcane remain the control plane without turning into a scheduler or cloud API wrapper itself.

## What A Provider Backend Is

A provider backend is the thing that turns high-level Arcane requests into real infrastructure actions.

Examples:

- create a cluster
- launch a serving service
- submit a training job
- report readiness / status
- stop and clean up resources

Provider backends are not the place where policy versioning, rollout draining, or training window semantics live. Those remain Arcane control-plane concerns.

## What Provider Backends Should Manage

Provider backends should manage three kinds of resources.

### 1. Clusters

Cluster-like compute allocations or machine groups.

Examples:

- rented GPU nodes
- cloud VM groups
- Slurm allocations
- future k8s node or pool abstractions if needed

### 2. Services

Longer-lived endpoints.

Examples:

- `vLLM` serving deployment
- auxiliary inference service
- future rollout coordinator service if needed

### 3. Jobs

Finite compute executions.

Examples:

- training runs
- preprocessing / export jobs
- one-off setup jobs

## Suggested Interface

The first useful interface is intentionally CRUD-like.

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

This interface is deliberately simple.
The point is not to perfectly model every backend.
The point is to give Arcane one clean place to ask for realization of services and jobs.

## Suggested Specs

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

These are intentionally backend-agnostic wrappers around “what should be made real.”

## Handles And Status

Arcane needs stable handles back from providers.

### `ClusterHandle`

Should include:

- Arcane-visible ID
- provider external ID
- metadata useful for later lookup

### `ServiceHandle`

Should include:

- service ID
- provider external ID
- endpoint if available
- readiness metadata

### `JobHandle`

Should include:

- job ID
- provider external ID
- state / status
- metadata

Provider-specific details can live in metadata, but Arcane should have stable top-level fields for lifecycle tracking.

## Readiness Requirements

Provider backends must be able to answer when a resource is ready enough for Arcane to proceed.

### For services

Arcane typically needs:

- endpoint
- health
- readiness
- backend metadata

### For jobs

Arcane typically needs:

- accepted / queued / running / finished / failed
- log or metrics pointer if available

This is important because a managed `ModelTarget` is not truly usable until a provider backend returns a live service endpoint.

## How This Fits The Control Plane

The control plane should do things like:

- decide a `ServingDeployment` should exist
- decide a `TrainingJob` should exist
- decide a `RolloutGroup` should target a certain policy version

The provider backend then does:

- create cluster if needed
- create service if needed
- submit job if needed

That means the control plane owns:

- lifecycle intent
- domain state
- transitions

The provider backend owns:

- infra realization
- external IDs
- operational status

## What Provider Backends Should Not Own

Provider backends should not own:

- policy version semantics
- rollout group state machine
- training window sealing
- benchmark/eval meaning
- serving promotion logic

Those are Arcane concerns.

## Recommended First Implementations

This doc does not force a single provider backend choice, but it does assume the following likely progression:

- one first practical cloud-oriented provider backend
- later optional backends for Slurm, Kubernetes, or other orchestrators

That means the interface should be shaped by what Arcane needs, not by the quirks of any one scheduler.

## Final Position

Provider backends are the realizers of control-plane intent.

Arcane should tell them:

- create this service
- submit this job
- stop this resource

and they should return:

- stable handles
- readiness/status
- enough metadata for Arcane to track lifecycle cleanly
