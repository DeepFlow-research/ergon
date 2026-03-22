# Control Plane State Machine

## Purpose

This document specifies the core state machines Arcane should own as part of the control plane.

The goal is to prevent the async RL and runtime-control-plane design from remaining hand-wavy around lifecycle.

The most important design principle is:

- environment plane executes
- serving plane serves
- training plane updates
- control plane owns lifecycle transitions

## Why This Matters

Without explicit state machines, the system will eventually end up encoding:

- rollout draining
- policy promotion
- training window sealing
- serving cutover

as a pile of ad hoc flags and one-off conditions.

That is exactly the kind of thing that causes a second redesign later.

## `RolloutGroupState`

The first and most important state machine is rollout group lifecycle.

### States

- `RUNNING`
- `PAUSED`
- `DRAINING`
- `STOPPED`

### Meaning

#### `RUNNING`

- new rollout work may be assigned
- in-flight work continues

#### `PAUSED`

- no new work is assigned
- operator / control-plane pause
- in-flight work handling may depend on policy

#### `DRAINING`

- no new work is assigned
- in-flight work is allowed to finish
- group is preparing for a coherent seal boundary

This is the key async-RL coordination state.

#### `STOPPED`

- no new work
- no expectation of continuation

### Allowed transitions

- `RUNNING -> PAUSED`
- `RUNNING -> DRAINING`
- `RUNNING -> STOPPED`
- `PAUSED -> RUNNING`
- `PAUSED -> DRAINING`
- `PAUSED -> STOPPED`
- `DRAINING -> STOPPED`

`DRAINING -> RUNNING` should generally not be the default path; creating a fresh rollout group or explicitly resuming after a controlled action is usually clearer.

## `PolicyVersionState`

Policy versions should be immutable in content, but they still have lifecycle state.

### States

- `REGISTERED`
- `SERVING`
- `DEPRECATED`
- `ARCHIVED`

### Meaning

#### `REGISTERED`

- known to Arcane
- not necessarily serving yet

#### `SERVING`

- currently valid for new rollout assignment

#### `DEPRECATED`

- do not attach to new rollout groups
- historical runs remain valid

#### `ARCHIVED`

- retained only for history / provenance

### Important invariant

Rollouts always point to an immutable policy version, never to a mutable “current model.”

## `TrainingWindowState`

Training windows define sealed training input.

### States

- `OPEN`
- `SEALED`
- `TRAINING`
- `CONSUMED`

### Meaning

#### `OPEN`

- candidate window still accumulating or not yet frozen

#### `SEALED`

- exact data boundary frozen
- eligible for training

#### `TRAINING`

- currently being used by one or more training jobs

#### `CONSUMED`

- training complete and window considered spent for the intended flow

### Important invariant

Once a window is `SEALED`, its membership should not drift.

## `TrainingJobState`

Training jobs need a basic lifecycle too.

### States

- `CREATED`
- `SUBMITTED`
- `RUNNING`
- `SUCCEEDED`
- `FAILED`
- `CANCELLED`

### Meaning

Arcane should be able to distinguish:

- internal control-plane creation
- provider/backend submission
- actual runtime execution
- terminal outcome

This matters because provider backends often acknowledge a job before it is truly running.

## `ServingDeploymentState`

Serving deployments represent the realized serving path for a policy version.

### States

- `CREATED`
- `STARTING`
- `READY`
- `FAILED`
- `STOPPED`

### Meaning

The control plane should not assume a policy version is usable for rollouts until its serving deployment is `READY`.

This is especially important for managed local models.

## Cross-Resource Coordination

These state machines matter most when coordinated together.

### Example: train on `v_k`

1. `PolicyVersion(v_k)` is `SERVING`
2. `RolloutGroup(rg_k)` is `RUNNING`
3. control plane decides to train
4. `RolloutGroup(rg_k)` -> `DRAINING`
5. in-flight work finishes
6. `TrainingWindow(w_k)` -> `SEALED`
7. `TrainingJob(t_k)` -> `RUNNING`
8. training succeeds
9. `PolicyVersion(v_{k+1})` -> `REGISTERED`
10. `ServingDeployment(sd_{k+1})` -> `READY`
11. `PolicyVersion(v_{k+1})` -> `SERVING`
12. `PolicyVersion(v_k)` -> `DEPRECATED`
13. new rollout groups attach to `v_{k+1}`

This is the concrete reason these state machines need to exist explicitly.

## Why `DRAINING` Is Special

This state deserves emphasis because it is the bridge between:

- ongoing asynchronous environment execution
- coherent training windows

If Arcane only had `PAUSED`, then there would be no clean state that means:

- stop assigning new work
- let in-flight work complete
- prepare a precise seal boundary

That would push an important RL coordination concept into ad hoc application logic. It should be first-class instead.

## Minimal API Implications

The state machine implies the need for control operations like:

```python
set_rollout_group_state(group_id, RolloutGroupState.DRAINING)
seal_training_window(group_ids=[...])
launch_training(window_id, trainer_spec)
register_policy_version(...)
promote_policy_version(version)
```

The exact endpoints can vary, but these transitions need first-class representation somewhere.

## Final Position

If Arcane is going to own the control plane, it must own explicit lifecycle state machines for:

- rollout groups
- policy versions
- training windows
- training jobs
- serving deployments

Without these, the architecture will look clean in docs but drift into ad hoc coordination in code.
