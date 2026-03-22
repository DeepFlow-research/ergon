# Control Flow: 70B RL Training Setup

## Goal

This document sketches how the four-plane design should behave when Arcane is used in a serious RL setting, such as:

- serving a large local model
- collecting rollouts on benchmark environments
- training on those trajectories
- promoting new policy versions without rebuilding the whole system

The goal is not to define every backend detail.
The goal is to make the control flow and ownership boundaries explicit now so the public API and persistence model do not have to be rebuilt later.

## Scenario

Assume:

- a 70B parameter policy is being served behind a self-hosted inference endpoint
- Arcane is being used to generate environment interactions and rewards
- a training backend consumes those trajectories and produces updated checkpoints
- rollouts and training overlap asynchronously, but with explicit control-plane coordination

## Core Actors

### Control Plane

Owns:

- rollout group lifecycle
- policy version lifecycle
- training window sealing
- training job creation
- serving cutover decisions

### Environment Plane

Owns:

- benchmark workflow execution
- tool / sandbox transitions
- reward / evaluator logic
- trace capture

### Serving Plane

Owns:

- current policy endpoint
- immutable served policy versions

### Training Plane

Owns:

- consuming trajectories
- computing updates
- publishing checkpoints

## Happy Path

### Step 1: Register policy version `v_k`

The control plane records:

- `policy_id`
- `policy_version = v_k`
- artifact pointer
- serving metadata

At this point, the policy version is immutable.

### Step 2: Bring up serving for `v_k`

The serving plane exposes an endpoint for `v_k`.

Arcane does not need to know how that happened in detail.
It only needs:

- endpoint
- version
- serving config
- health/readiness

### Step 3: Create rollout group `rg_k`

The control plane creates a rollout group attached to:

- `EvalSpec`
- `policy_version = v_k`
- concurrency target
- staleness / grouping rules if needed

The rollout group starts in `RUNNING`.

### Step 4: Rollout execution begins

The environment plane receives or leases rollout work under `rg_k`.

For each rollout:

1. assemble observation
2. call serving endpoint for `v_k`
3. apply tool/environment transitions
4. capture trace events
5. compute rewards and terminal state
6. persist rollout output

Each trace / rollout / episode is stamped with:

- `policy_version = v_k`
- benchmark/environment version
- serving config

This is the key provenance invariant.

### Step 5: Accumulate trajectories

The control plane watches completion counts, trace availability, or other thresholds.

Once enough data exists, it creates a training window candidate from:

- rollout group(s)
- trajectory filters
- reward / quality filters

This is still only metadata until the window is sealed.

### Step 6: Drain rollout group

When it is time to train, the control plane should usually move the group to `DRAINING`, not hard stop it.

Meaning:

- do not assign new rollout work
- allow in-flight episodes to complete
- keep provenance clean
- avoid mixed half-finished windows

Once all inflight work finishes, the group’s data window can be sealed.

### Step 7: Seal training window

The control plane seals a `TrainingWindow` with:

- source policy version `v_k`
- included rollout groups or episode filter
- exact trace selection boundary

After sealing, this window becomes the canonical training input.

### Step 8: Launch training job

The training plane is invoked with:

- training window reference
- source checkpoint `v_k`
- trainer config
- destination output location

Arcane does not need to own the optimizer implementation.
It only needs a durable control-plane object for the training job and its outputs.

### Step 9: Produce `v_{k+1}`

Training finishes and emits:

- new checkpoint
- trainer metrics
- optional reward metrics / eval summaries

The control plane registers a new immutable policy version:

- `v_{k+1}`

### Step 10: Update serving

The control plane initiates serving cutover:

- start serving `v_{k+1}`
- verify readiness
- switch new rollout groups to `v_{k+1}`

Importantly:

- old rollouts from `v_k` do not get relabeled
- new rollouts should not silently mix versions

### Step 11: Resume rollout scheduling

The control plane creates or resumes rollout groups against `v_{k+1}`.

This may mean:

- reusing the same eval spec
- creating a new rollout group generation
- preserving experiment lineage while rotating policy version

## Why Drain Matters

This is one of the most important behaviors to specify now.

If the system only has:

- `pause`
- `resume`

then it lacks the clean async RL behavior of:

- stop assigning new work
- let existing work finish
- seal a coherent training window

That is why `DRAINING` should be a first-class rollout-group state.

It is the correct control-plane mechanism for synchronized-but-async training boundaries.

## Why Serving And Training Are Separate Here

In this control flow:

- serving owns inference for `v_k`
- training produces `v_{k+1}`
- control plane decides when the switch happens

This avoids:

- mutating weights mid-rollout
- mixed-version episodes
- freezing all environment execution unnecessarily
- coupling inference uptime to trainer process lifecycle

This is exactly why serving and training should not be collapsed into one plane.

## Suggested Core APIs

These are not complete APIs, but the control flow strongly suggests the need for operations like:

```python
create_rollout_group(eval_spec, policy_version, dispatch) -> RolloutGroup
set_rollout_group_state(group_id, state) -> RolloutGroup
seal_training_window(group_ids, source_policy_version, filters) -> TrainingWindow
launch_training(window_id, trainer_spec) -> TrainingJob
register_policy_version(training_job_result) -> PolicyVersion
promote_policy_version(policy_version, serving_target) -> ServingDeployment
```

If these are not represented somewhere, the system will likely re-invent them awkwardly later.

## What Can Stay Unspecified For Now

This design does **not** require the following to be fully nailed down today:

- whether rollout workers are processes, jobs, pods, or inline workers
- whether serving runs via vLLM, custom server, or remote provider
- whether training launches via Slurm, Kubernetes, or a local runner
- the exact queueing mechanism

Those are implementation choices.

The important thing to specify now is the control-plane state and sequencing model.

## What Must Be Specified Now

To avoid a near-term rebuild, the following should be specified now:

1. `PolicyVersion` as a first-class immutable object
2. `RolloutGroup` as a first-class schedulable object
3. `TrainingWindow` as a sealed training unit
4. rollout group states including `DRAINING`
5. serving cutover semantics
6. policy provenance on every rollout/trace

Those are the stable bones of the system.

## Recommended V1 Concrete Path

The long-term design allows many different backend realizations, but it is still worth writing down one practical first implementation.

### Recommended v1 stack

- Arcane control plane and environment runtime
- one concrete cloud GPU launch provider
- `vLLM` as the first serving backend for large local models
- one concrete training runtime/backend path
- provider-hosted or existing remote APIs for simple baseline evals

The main goal of this first stack is not to be universally portable. It is to prove the control-plane model against one serious local-model path while keeping the abstractions clean enough that later backends can slot in.

### Why this is the right first step

For a first implementation, the bottleneck is not having every scheduler backend available. The bottleneck is having one path that really works for:

- local or rented GPU serving
- benchmark/eval execution
- trajectory collection
- training handoff
- policy version promotion

That is much easier to make real with one pragmatic launch provider and one serving/training stack than by trying to be natively multi-backend from the start.

## Concrete V1 Realization

### Serving

For a large model such as a 70B checkpoint, the first serving backend should likely be `vLLM`.

The control plane should say:

- create serving deployment for `policy_version = v_k`

The provider backend should then:

- provision or attach to the required hardware
- launch the `vLLM` service
- wait for health/readiness
- return an endpoint and deployment handle

Arcane then records:

- endpoint
- serving backend = `vllm`
- policy version
- readiness status

### Training

For training, the first concrete path should be one training runtime/backend combination that you actually expect to use, rather than a broad abstraction-first matrix.

The important thing is that the control plane can:

- seal a training window
- ask the provider/runtime backend to launch training
- track training job status
- register the resulting checkpoint as `v_{k+1}`

Whether the first concrete trainer uses Ray under the hood or a backend-native launcher is less important than making sure one path is real end-to-end.

### Why not Slurm-first

Slurm is a completely reasonable future backend, but unless the real operating environment is already Slurm-native, it does not need to be the first concrete implementation.

The first concrete path should be the cheapest, fastest route to:

- multi-GPU or multi-node serving/training
- a real model endpoint
- a real policy version lifecycle
- a real training handoff

This may be a cloud GPU provider plus one concrete launch runtime rather than Slurm-first.

## Future Backend Variants

Once the control-plane model is proven, the same flow should be realizable later through:

- Slurm-backed training and serving
- Kubernetes-based serving
- SkyPilot-style cloud orchestration
- alternate trainer backends

But those are future backend substitutions over the same control flow, not new architecture.

## Relationship To Near-Term Eval Ergonomics

This may seem more ambitious than the immediate evaluation ergonomics work, but it does not contradict it.

Near-term:

- users interact with `EvalSpec + ModelTarget`

Longer-term:

- the control plane internally turns those into rollout groups and policy-version-bound execution

So the user-facing API can stay simple while the internal architecture remains async-RL-compatible.

## Final Position

For a 70B RL-style setup, the right model is:

- environment plane executes
- serving plane serves immutable versions
- training plane creates new versions
- control plane owns pause/drain/train/promote lifecycle

That is the control flow Arcane should be designed around.
