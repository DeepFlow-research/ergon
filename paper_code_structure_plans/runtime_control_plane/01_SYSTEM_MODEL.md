# System Model

## Executive View

Arcane should not be modeled as a Python library that also happens to run some services.

Arcane should be modeled as a system with four planes:

1. **Control plane**
2. **Environment plane**
3. **Serving plane**
4. **Training plane**

The key architectural move is to make the control plane explicit rather than letting the environment runtime absorb lifecycle, orchestration, and policy-version responsibilities indirectly.

## Why Four Planes

The older three-plane framing was:

- environment
- serving
- learning

That is directionally right, but it hides the most important coordination logic.

Somebody has to decide:

- when new rollouts may begin
- when in-flight rollouts should drain
- when enough trajectories are ready for training
- which policy version is active for new work
- when serving should switch to a new checkpoint
- how policy provenance is recorded and exposed

That is not environment behavior.
That is not serving behavior.
That is not training behavior.

That is **control-plane behavior**.

## Plane Responsibilities

### 1. Control Plane

This is the system brain.

Responsibilities:

- accept evaluation and training-oriented submissions
- create and manage rollout groups
- attach policy versions to rollout groups
- manage rollout group state:
  - `RUNNING`
  - `PAUSED`
  - `DRAINING`
  - `STOPPED`
- decide when training windows are sealed
- launch or coordinate training jobs
- register new policy versions
- decide when new rollouts should target a new policy version
- coordinate serving cutovers
- expose experiment/run/cohort/control APIs

The control plane is the authoritative place for lifecycle and versioning decisions.

It should also own **dispatch intent** as a domain concept. That means it decides that:

- serving for a policy version should exist
- rollout capacity should exist
- a training job should be launched
- a rollout group should drain or pause

But it does not need to become the low-level scheduler or cloud API wrapper itself. Job execution can be delegated to provider backends.

## Control Plane Vs Provider Backends

This distinction should be explicit.

### Control plane owns intent and lifecycle

The control plane should own:

- what should run
- when it should run
- which policy version it should use
- when rollout groups should drain
- when training windows are sealed
- when new policy versions are promoted

These are domain decisions.

### Provider backends own realization

Provider backends should own:

- provisioning hardware
- creating and destroying clusters
- launching jobs
- launching services
- surfacing readiness and status
- cleaning up provider-managed resources

These are infrastructure execution concerns.

Arcane should therefore be able to say:

- "bring up serving for `v_k`"
- "launch a trainer for this training window"
- "ensure rollout capacity exists"

without itself becoming an HPC scheduler or cloud resource manager.

### 2. Environment Plane

This is Arcane’s core runtime.

Responsibilities:

- benchmark and workflow execution
- tool execution
- sandbox execution
- stakeholder simulators
- observation assembly
- reward and evaluator execution
- trace capture
- persistence of environment-side execution facts

The environment plane should be policy-version-aware, but not policy-lifecycle-authoritative.

It should know which policy version a rollout is using.
It should not decide when training happens or when serving should switch.

### 3. Serving Plane

This is the inference system for the current policy version.

Examples:

- OpenAI / Anthropic provider calls
- vLLM
- a self-hosted generation service
- future clustered serving

Responsibilities:

- serve a specific policy version
- generate model outputs from observations
- optionally expose logprobs
- optionally expose streaming deltas
- remain stable while the environment plane consumes it

The serving plane is the read path for the model.

### 4. Training Plane

This is the system that updates policies.

Examples:

- TRL
- OpenRLHF
- veRL
- a custom trainer

Responsibilities:

- consume sealed training windows / exports
- compute losses and updates
- produce new checkpoints
- report training metrics
- return or register policy artifacts

The training plane is the write path for the model.

## Core Principle

The serving plane and training plane are different because they do opposite things:

- serving uses an immutable policy version
- training creates the next policy version

Async RL only works cleanly if those two concerns are separated by explicit policy versioning and control-plane coordination.

## Core Objects Arcane Should Own

Arcane should have first-class persistent objects roughly like these.

### `PolicyVersion`

Immutable identity for a rollout policy.

Suggested fields:

- `policy_id`
- `version`
- `artifact_uri`
- `metadata`
- `serving_config`
- `created_at`
- `status`

### `ModelTarget`

User-facing or runtime-facing reference to the current model source.

Suggested fields:

- `kind`: `provider` | `endpoint` | `managed`
- `model_name`
- `version`
- `provider`
- `endpoint`
- `generation_config`
- optional `launch`

### `EvalSpec`

Stable statement of what to run.

Suggested fields:

- benchmark
- workflow
- split
- experiment IDs
- task IDs
- limit
- cohort name
- timeout
- max questions

### `RolloutGroup`

Schedulable unit of environment work.

Suggested fields:

- `id`
- `eval_spec`
- `policy_version`
- `desired_state`
- `max_concurrency`
- `created_at`
- `metadata`

### `TrainingWindow`

Sealed unit of trajectories to train on.

Suggested fields:

- `id`
- `source_policy_version`
- `trace_filter`
- `status`
- `created_at`
- `sealed_at`

### `TrainingJob`

Execution of training over one or more windows.

Suggested fields:

- `id`
- `trainer_backend`
- `source_policy_version`
- `output_policy_version`
- `status`
- `metrics`
- `artifact_refs`

### `ServingDeployment`

Current serving realization of a policy.

Suggested fields:

- `id`
- `policy_version`
- `endpoint`
- `backend`
- `status`
- `metadata`

### `ProviderResource`

Arcane will likely need an internal record of provider-managed resources even if provider backends stay lightly abstracted.

Suggested fields:

- `id`
- `provider_kind`
- `resource_type`: cluster | job | service
- `external_id`
- `status`
- `metadata`

## State Machines

### Rollout Group State

Minimum state machine:

- `RUNNING`
- `PAUSED`
- `DRAINING`
- `STOPPED`

Semantics:

- `RUNNING`: can schedule new rollout work
- `PAUSED`: do not schedule new work; existing work may or may not continue depending on policy
- `DRAINING`: do not schedule new work; allow in-flight work to finish
- `STOPPED`: no new work and no expectation of continuation

`DRAINING` is important. It is not the same as `PAUSED`.
It is the clean async-RL control action for "finish what is in flight, then seal the window."

### Policy Version Lifecycle

Suggested lifecycle:

- `REGISTERED`
- `SERVING`
- `DEPRECATED`
- `ARCHIVED`

The key invariant is that rollouts always point to an immutable version, never to a mutable "current model."

## Runtime Submission Boundary

Serious execution should enter Arcane through a serialized request.

Core request shape:

```python
class WorkflowSubmissionRequest(BaseModel):
    eval: EvalSpec
    model: ModelTarget
    dispatch: DispatchSpec
```

The control plane receives this and decides:

- whether the model target is already live
- whether anything needs to be provisioned
- which rollout group to create
- what policy version should be attached

## What Lives Outside Arcane

Arcane should not own everything.

It should integrate with, not absorb:

- serving engines
- trainer frameworks
- cluster launchers
- checkpoint artifact systems

That keeps the control plane durable and framework-agnostic.

## What Arcane Must Record

To remain compatible with future RL and training systems, Arcane must record at least:

- which policy version produced a rollout
- which serving configuration was active
- which benchmark/environment version was active
- exact environment-side trace ordering
- reward / evaluation outcomes

This is the minimum provenance contract that prevents a later redesign.

## Near-Term Focus

Even though the four-plane model includes rollout groups and training windows, the immediate ergonomic target remains narrower:

- make evaluation stable through `EvalSpec`
- make model choice swappable through `ModelTarget`
- keep the submission boundary clean
- keep the control plane responsible for versioning and lifecycle

That gives Arcane room to grow into async RL without forcing the entire RL control loop to be fully implemented on day one.

## Final Position

The environment plane should not be the hidden owner of experiment lifecycle.

The clean model is:

- **control plane** decides
- **environment plane** executes
- **serving plane** generates
- **training plane** updates

Provider backends then sit beneath the control plane as realizers of serving/training/cluster intent rather than as first-class domain owners.

That is the system model this doc recommends.
