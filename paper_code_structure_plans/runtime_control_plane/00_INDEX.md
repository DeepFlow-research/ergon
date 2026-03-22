# Runtime Control Plane Design Set

This folder replaces the earlier runtime control plane notes with a tighter, more coherent set of design docs.

The goal of this set is to answer five questions clearly:

1. What are the core planes and responsibilities?
2. What does the control flow look like for serious RL-style training and evaluation?
3. What should the public API feel like?
4. How opinionated should Arcane be about deployment and orchestration?
5. What are the main user stories we want to support cleanly?

## Documents

### `01_SYSTEM_MODEL.md`
Top-level architecture and the four-plane model:

- control plane
- environment plane
- serving plane
- training plane

Also defines the core persistent objects and state transitions that Arcane should own.

### `02_CONTROL_FLOW_70B_RL.md`
Concrete end-to-end control flow for running RL with a large local model, including:

- policy versioning
- rollout group creation
- draining / pausing semantics
- trainer handoff
- serving cutover

### `03_PUBLIC_API_NAPKIN.md`
Code-shaped public API sketch. Includes:

- `EvalSpec`
- `ModelTarget`
- `LaunchSpec`
- `ArcaneClient`
- control-plane resource types

### `04_DEPLOYMENT_AND_ORCHESTRATION_STANCE.md`
What Arcane should and should not take a stance on regarding:

- Compose
- Kubernetes
- Slurm
- SkyPilot
- declarative configs vs programmable orchestration

### `05_USER_STORIES.md`
Concrete user flows for:

- cloud API evals
- local served model evals
- managed local model launch
- async RL training loops
- future training-produced policy evaluation

### `06_PROVIDER_BACKENDS.md`
Concrete provider/backend interface sketch covering:

- launch providers
- cluster / job / service handles
- CRUD-style lifecycle expectations
- how provider backends hand live endpoints and job status back to Arcane

### `07_V1_CONCRETE_IMPLEMENTATION.md`
Recommended first concrete stack for actually building the system, including:

- one pragmatic launch provider choice
- serving backend choice
- training backend/runtime choice
- what is intentionally deferred

### `08_CONTROL_PLANE_STATE_MACHINE.md`
Explicit lifecycle/state-machine doc for:

- rollout groups
- policy versions
- training windows
- training jobs
- serving deployments

### `09_REST_AND_SDK_CONTRACTS.md`
Request/response contract sketch tying together:

- Python SDK surface
- REST endpoints
- serialized runtime submission payloads
- visibility boundaries between public and internal types

## Design Position

The main position across these docs is:

- Arcane should be the **control plane and environment runtime**
- serious execution should go through the Arcane runtime/API
- the API should optimize first for **clean eval ergonomics over swappable model targets**
- the architecture should already leave room for async RL without requiring all rollout/trainer backends to be implemented now

## Intended Outcome

After reading this folder, the intended conclusion should be:

- what Arcane owns
- what Arcane delegates
- what the API should feel like
- how a larger RL system fits around Arcane
- what one concrete v1 implementation should actually look like
