# V1 Concrete Implementation

## Goal

This document answers the practical question:

**if we had to build one real version of this system now, what would we actually choose?**

The point is not to commit forever to one backend.
The point is to remove ambiguity and make the first serious implementation path explicit.

## Recommended V1 Stack

### Control plane

- Arcane runtime/API
- Postgres for canonical metadata
- Redis if/when hot-path coordination is needed

### Environment plane

- existing Arcane benchmark/workflow runtime
- current tool/sandbox model, upgraded over time

### Serving plane

- `vLLM` as the first concrete serving backend for large local models

### Training plane

- one concrete training runtime/backend path that is actually expected to be used

### Provider backend

- one first practical cloud-oriented `LaunchProvider`

## Why This Is The Right V1

This stack gives you a credible path for:

- evaluating against provider models
- evaluating against already-live local endpoints
- launching a large local model
- collecting traces/rewards
- running a training job
- registering a new policy version

without pretending to solve every deployment backend at once.

## Recommended First Provider Bias

The first provider backend should optimize for:

- easy access to rented GPU hardware
- practical time-to-value
- minimal operational ceremony
- ability to support serious serving/training experiments quickly

Unless your actual environment is already HPC-native, this likely means:

- cloud GPU acquisition first
- Slurm later

The concrete provider can be whichever public cloud GPU path you are realistically going to use first. The important thing is that it gives Arcane a real cluster/job/service path without forcing the architecture to become provider-specific.

## Recommended First Serving Backend

For a large local model such as a 70B checkpoint, `vLLM` is the recommended first serving backend.

Why:

- it directly matches the serving-plane abstraction
- it is a practical endpoint-based serving system
- it keeps the serving problem separate from the training problem
- it makes `ModelTarget(kind="endpoint" | "managed")` concrete immediately

Arcane should not try to invent its own serving stack for v1.

## Recommended First Training Path

The first training path should be exactly one real one.

The control-plane requirement is only:

- seal a training window
- launch training
- track job status
- register the result as a new `PolicyVersion`

How training is implemented underneath can be delegated.

The important v1 decision is not to expose ten backend options. It is to pick one training runtime/backend path and make the control-plane contract around it correct.

## Recommended Operational Split

### What Arcane owns

- eval submission
- model target submission
- policy version registration
- rollout group creation
- rollout draining
- training window sealing
- training job records
- serving deployment records

### What the provider backend owns

- create cluster
- create service
- submit training job
- return readiness and status
- clean up resources

### What the serving backend owns

- host the model
- expose endpoint
- serve completions/logprobs

### What the training backend owns

- consume training input
- update weights
- produce checkpoint

## Recommended V1 User Paths

The first implementation should fully support:

1. provider model evals
2. existing endpoint evals
3. managed local model launch for evals
4. sealed training window -> training job -> new policy version

That is enough to validate the architecture.

## What V1 Explicitly Does Not Need

V1 does not need:

- Slurm-native orchestration
- Kubernetes-native orchestration
- multiple launch providers
- multiple training runtimes
- rollout-worker fleet abstraction as a polished product
- full async RL policy freshness strategy beyond the basic control-plane state machine

Those can come later.

## Why This Is Better Than A Broader V1

A broader v1 would feel more "general," but in practice it would slow down the one thing you need:

- proving the control-plane model against one real large-model workflow

The fastest way to learn whether the architecture is right is:

- choose one provider path
- choose one serving path
- choose one training path
- make policy versioning and lifecycle semantics real

That is more valuable than trying to be complete.

## Final Position

The recommended v1 is:

- Arcane control plane
- Arcane environment runtime
- one practical cloud-oriented `LaunchProvider`
- `vLLM` serving
- one concrete training backend/runtime path

This is the minimum real system that can validate the larger architecture without overcommitting to all future backends.
