# Deployment And Orchestration Stance

## Executive Position

Arcane should take a **strong stance on the runtime API and control-plane model**, but only a **light stance on deployment and orchestration backends**.

In other words:

- be opinionated about what a run, eval, model target, policy version, rollout group, and training window mean
- be less opinionated about whether serving or training is launched by Compose, Slurm, Kubernetes, SkyPilot, or something else

That is the best way to avoid overfitting the system to local dev while still making local dev pleasant.

## Why This Matters

There are two opposite failure modes here.

### Failure mode 1: too little stance

If Arcane says nothing about lifecycle, policy versioning, or run semantics, then every later serving/training integration ends up inventing its own contracts.

That leads to:

- provenance drift
- hidden state machines
- inconsistent control semantics
- a likely rebuild later

### Failure mode 2: too much stance in the wrong place

If Arcane takes too strong a stance on:

- Compose
- Slurm launch syntax
- Kubernetes manifests
- exact trainer invocation mechanics

then local convenience leaks into the core architecture and constrains the future.

The right balance is:

- strong domain stance
- light backend stance

## What Arcane Should Be Strongly Opinionated About

Arcane should strongly define:

- `EvalSpec`
- `ModelTarget`
- `PolicyVersion`
- `RolloutGroup`
- `TrainingWindow`
- serving cutover semantics
- rollout group states including `DRAINING`
- provenance requirements for runs and traces

These are domain concepts. They should be stable and explicit.

## What Arcane Should Be Loosely Opinionated About

Arcane should be loosely opinionated about:

- how a model endpoint gets launched
- how GPUs are provisioned
- whether a launcher is Slurm, Kubernetes, Compose, or SkyPilot
- whether training runs through TRL, OpenRLHF, veRL, or something custom

These are integration concerns. Arcane should define enough interface to interoperate with them, but should not absorb them all into its core domain model.

## Compose

### Stance
Compose is a local development convenience.

### What it should mean

- boot Arcane locally
- boot supporting infra locally
- optionally boot a local model-serving endpoint

### What it should not mean

- the conceptual deployment model for Arcane
- the core abstraction the public API is written around
- the thing that defines how future trainer or rollout systems work

Compose should live under something like:

- `dev`
- `runtime up`
- `runtime down`

not as the defining conceptual center of the system.

## Slurm

### Stance
Arcane should remain compatible with Slurm-backed serving or training, but should not force a Slurm-centric API into the core user model.

### What that means

Users should not have to think in terms of:

- partitions
- job arrays
- allocation details

unless they are explicitly using a managed launch path.

Those details belong under `LaunchSpec.launcher_config`, not in `EvalSpec`.

## Kubernetes / SkyPilot

### Stance
These should be seen as future backend realizations of serving and training integration, not as core domain concepts.

The runtime API should be indifferent to whether the model endpoint came from:

- a provider
- a pod
- a Slurm job
- a SkyPilot deployment

The important thing is that Arcane receives a valid `ModelTarget` and records the correct provenance.

## Declarative vs Programmable

This is an important product decision.

The user explicitly does **not** want Arcane to become too "declarative" in the sense of requiring a giant orchestration manifest for every workflow.

I think the right stance is:

- keep the **core SDK programmable**
- keep the **runtime API spec-based**
- allow **optional declarative configs** for repeatable launch scenarios

So:

- Python SDK for day-to-day control
- optional YAML or config files for repeatable experiment/serving launch patterns

This gives you both:

- ergonomic interactive use
- reproducible operational entrypoints

without forcing one style onto every user.

## Recommended Pattern

### The user-facing pattern

The user should be able to do this in Python:

```python
await client.evaluate(
    eval_spec,
    model=model_target,
)
```

and also this in config-driven form:

```bash
magym eval run -f experiment.yaml
```

where the YAML is just a serialized version of the same underlying concepts.

### The internal pattern

Internally, Arcane should only really care about:

- normalized runtime specs
- stable control-plane objects
- versioned model provenance

The launcher backend should be an implementation detail behind a managed `ModelTarget` or related control-plane action.

## What To Avoid

Avoid:

- putting Slurm- or K8s-specific fields directly into `EvalSpec`
- making scheduler-specific semantics part of the default evaluation path
- letting local Compose ergonomics define the core architecture
- forcing users to choose orchestration mechanics when they just want to evaluate a model

Those are all signs that the integration layer is bleeding upward into the user-facing domain model.

## Recommended Product Stance

The best near-term stance is:

1. Arcane is opinionated about evaluation and control-plane semantics.
2. Arcane is flexible about how model endpoints are realized.
3. Arcane supports both programmable and declarative entrypoints.
4. Arcane avoids making backend-specific orchestration the main thing users interact with.

## Recommended V1 Backend Stance

Even though Arcane should remain backend-flexible in principle, v1 still needs one concrete implementation of each key path.

The recommended stance for v1 is:

- one concrete `LaunchProvider`
- one concrete serving backend
- one concrete training runtime/backend path
- Compose only for local development convenience

The point is not to be universally portable on day one. The point is to validate the control-plane design against one serious real-world setup.

### Recommended v1 bias

Unless the real operating environment is already Slurm-native, the first concrete implementation should probably not be Slurm-first.

A more pragmatic v1 is:

- cloud GPU acquisition through one provider backend
- `vLLM` for serving
- one training backend/runtime that you actually expect to use
- Arcane control plane on top of those

That gets you to a real "serve local model, run evals, collect traces, train, register new policy version" loop faster than trying to be deeply HPC-native immediately.

## Why Not Slurm First

This is not an argument against Slurm. It is an argument against making Slurm your first forced concrete path unless that is already your actual operating environment.

Slurm is a future backend worth keeping room for, but a first implementation should optimize for:

- fastest time to one real end-to-end path
- minimal operational guesswork
- ability to provision the hardware you actually expect to rent or use
- a simple story for serving and training job realization

If cloud GPU providers are the likely real starting point, that should be reflected honestly in the v1 design.

## Dispatch Intent Vs Job Realization

This is the key conceptual split:

- Arcane owns **dispatch intent**
- provider backends own **job realization**

Meaning:

- Arcane decides that serving for `v_k` should exist
- Arcane decides that a training job for training window `w_k` should exist
- Arcane decides that rollout capacity for a rollout group should exist

But provider backends decide how those become:

- clusters
- services
- jobs
- endpoints

This keeps the control plane from turning into a cloud scheduler.

## Recommended Terminology

To make this clearer in docs and code, the following naming bias is recommended:

- `ModelTarget` for user-facing model selection
- `LaunchProvider` for infra/job/service realization
- `ServingDeployment` for a realized serving endpoint
- `TrainingJob` for control-plane tracking of training execution

This avoids overloading generic terms like `Provider` too early.

## Final Position

Arcane should be:

- **strict** about the meaning of evaluations, policy versions, rollout groups, and training windows
- **loose** about the mechanics of provisioning the systems that satisfy those contracts

That is the cleanest way to remain flexible without becoming vague.
