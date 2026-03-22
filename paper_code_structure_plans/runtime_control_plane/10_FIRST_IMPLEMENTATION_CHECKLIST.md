# First Implementation Checklist

## Purpose

This document translates the runtime control plane design set into:

- concrete code areas
- likely new modules
- likely rewrites or deletions
- a first PR sequence

The goal is not to freeze the exact implementation plan forever. The goal is to make it easy to start building without having to repeatedly re-derive the first steps from the higher-level docs.

## Design Docs This Implements

This checklist is derived from:

- `01_SYSTEM_MODEL.md`
- `02_CONTROL_FLOW_70B_RL.md`
- `03_PUBLIC_API_NAPKIN.md`
- `04_DEPLOYMENT_AND_ORCHESTRATION_STANCE.md`
- `05_USER_STORIES.md`
- `06_PROVIDER_BACKENDS.md`
- `07_V1_CONCRETE_IMPLEMENTATION.md`
- `08_CONTROL_PLANE_STATE_MACHINE.md`
- `09_REST_AND_SDK_CONTRACTS.md`

## High-Level Build Order

The shortest reasonable implementation order is:

1. introduce the new public submission types
2. add a new evaluation submission API path
3. persist `EvalSpec + ModelTarget + DispatchSpec`
4. resolve `ModelTarget` into runtime execution config
5. phase out live worker / process-local runtime assumptions from the new path
6. add control-plane internal objects and state
7. add one concrete provider backend
8. add one concrete serving path
9. add one concrete training path

The key principle is:

- build the new path alongside the old one
- make the new path coherent first
- only then remove older assumptions

## Current Code Areas Most Affected

These are the parts of the current codebase most likely to change first.

### Public-facing runtime/SDK surface

- `h_arcane/core/task.py`
- `h_arcane/core/worker.py`
- `h_arcane/core/runner.py`
- `h_arcane/__init__.py`

### Runtime submission and execution path

- `h_arcane/core/_internal/task/inngest_functions/benchmark_run_start.py`
- `h_arcane/core/_internal/task/inngest_functions/worker_execute.py`
- `h_arcane/core/_internal/task/worker_context.py`
- `h_arcane/core/_internal/task/persistence.py`
- `h_arcane/core/_internal/api/runs.py`
- `h_arcane/core/_internal/db/models.py`

### CLI / setup / local launcher

- `h_arcane/cli/main.py`
- services under `h_arcane/services/setup/`

### Contract generation / frontend surface

- `scripts/export_contract_schemas.py`
- `arcane-dashboard/scripts/generate-rest-contracts.mjs`
- `arcane-dashboard/src/lib/contracts/rest.ts`
- `arcane-dashboard/src/hooks/useRunState.ts`

## Proposed New Modules

These are suggested targets, not mandatory exact filenames.

### Public authoring/client modules

```text
h_arcane/sdk/evals.py
h_arcane/sdk/models.py
h_arcane/sdk/client.py
h_arcane/sdk/dispatch.py
```

Suggested contents:

- `EvalSpec`
- `ModelTarget`
- `LaunchSpec`
- `DispatchSpec`
- `ArcaneClient`
- `SubmittedRun`

### Internal control-plane modules

```text
h_arcane/core/control_plane/models.py
h_arcane/core/control_plane/service.py
h_arcane/core/control_plane/state_machine.py
```

Suggested contents:

- `PolicyVersion`
- `RolloutGroup`
- `TrainingWindow`
- `TrainingJob`
- `ServingDeployment`
- rollout/policy/training lifecycle helpers

### Provider backend modules

```text
h_arcane/core/providers/base.py
h_arcane/core/providers/models.py
h_arcane/core/providers/<v1_provider>.py
```

Suggested contents:

- `LaunchProvider`
- `ClusterSpec`
- `ServiceSpec`
- `JobSpec`
- handles and status objects
- first concrete provider implementation

### Serving / training adapter modules

```text
h_arcane/core/serving/base.py
h_arcane/core/serving/vllm.py
h_arcane/core/training/base.py
h_arcane/core/training/<v1_training_backend>.py
```

### Submission / API modules

```text
h_arcane/core/submission/models.py
h_arcane/core/submission/service.py
h_arcane/core/_internal/api/evals.py
```

## Current Modules To Shrink, Rewrite, Or Delete

### Likely shrink/rewrite heavily

- `h_arcane/core/runner.py`
- `h_arcane/core/task.py`
- `h_arcane/core/worker.py`
- `h_arcane/core/_internal/task/inngest_functions/benchmark_run_start.py`
- `h_arcane/core/_internal/task/inngest_functions/worker_execute.py`

### Likely delete from the new path

- `h_arcane/core/_internal/task/worker_context.py`

This is the file most directly tied to the old process-local worker registry assumption.

## First PR Sequence

The exact PR count can vary, but this is the sequencing I would recommend.

### PR 1: Add new SDK submission types

Add:

- `EvalSpec`
- `ModelTarget`
- `LaunchSpec`
- `DispatchSpec`
- `SubmittedRun`
- initial `ArcaneClient` shell

Likely files:

- `h_arcane/sdk/evals.py`
- `h_arcane/sdk/models.py`
- `h_arcane/sdk/dispatch.py`
- `h_arcane/sdk/client.py`
- `h_arcane/__init__.py`

Goal:

- create the new public surface without changing runtime internals yet

### PR 2: Add runtime submission API

Add:

- `POST /api/evals`
- submission models and service
- basic persistence of submitted request

Likely files:

- `h_arcane/core/submission/models.py`
- `h_arcane/core/submission/service.py`
- `h_arcane/core/_internal/api/evals.py`
- `h_arcane/core/_internal/db/models.py`

Likely DB additions:

- `Run.submission_spec_json`
- `Run.dispatch_spec_json`
- `Run.model_target_json` or equivalent

Goal:

- Arcane accepts the new request shape and persists it durably

### PR 3: Resolve `ModelTarget` in the runtime

Add:

- model target resolution logic
- provider vs endpoint vs managed branching
- initial model provenance persistence

Likely files:

- `h_arcane/core/submission/service.py`
- `h_arcane/core/control_plane/service.py`
- `h_arcane/core/providers/base.py`

Goal:

- the runtime can take `ModelTarget` seriously, even if only provider/endpoint are supported at first

### PR 4: Build first control-plane internal models

Add:

- `PolicyVersion`
- `RolloutGroup`
- `TrainingWindow`
- `TrainingJob`
- `ServingDeployment`

Likely files:

- `h_arcane/core/control_plane/models.py`
- `h_arcane/core/_internal/db/models.py`

Goal:

- create the internal lifecycle objects now, even if not all are user-visible yet

### PR 5: Add rollout-group state machine

Add:

- `RUNNING`
- `PAUSED`
- `DRAINING`
- `STOPPED`
- transition helpers

Likely files:

- `h_arcane/core/control_plane/state_machine.py`
- `h_arcane/core/control_plane/service.py`

Goal:

- avoid baking lifecycle transitions into ad hoc branches later

### PR 6: Add first concrete provider backend

Add:

- `LaunchProvider` base
- one concrete backend implementation

Likely files:

- `h_arcane/core/providers/base.py`
- `h_arcane/core/providers/models.py`
- `h_arcane/core/providers/<v1_provider>.py`

Goal:

- prove the dispatch-intent / job-realization split with one real backend

### PR 7: Add first concrete serving backend

Add:

- serving backend interface
- `vLLM` concrete implementation
- managed `ModelTarget` resolution path

Likely files:

- `h_arcane/core/serving/base.py`
- `h_arcane/core/serving/vllm.py`
- provider integration points

Goal:

- make the “managed local model” story real

### PR 8: Add first training backend/runtime integration

Add:

- training backend interface
- one concrete trainer runtime path
- control-plane `TrainingJob` handoff

Likely files:

- `h_arcane/core/training/base.py`
- `h_arcane/core/training/<v1_backend>.py`
- control-plane service updates

Goal:

- make `TrainingWindow -> TrainingJob -> PolicyVersion` a real loop

### PR 9: Port benchmark/eval flows to new submission path

Update:

- CLI benchmark/eval commands
- benchmark submission services
- older runtime entrypoints

Likely files:

- `h_arcane/cli/main.py`
- services under `h_arcane/services/setup/`
- `benchmark_run_start.py`

Goal:

- route new evals through the new API and control-plane model

### PR 10: Remove old process-local assumptions from serious path

Remove or deprecate:

- worker-in-task runtime dependency
- in-memory worker registry for serious runtime-backed execution

Likely files:

- `h_arcane/core/_internal/task/worker_context.py`
- `h_arcane/core/runner.py`
- `h_arcane/core/task.py`
- `h_arcane/core/worker.py`

Goal:

- stop carrying the old architectural contradiction in the main path

## Minimal Milestone Definitions

### Milestone A: New eval API exists

Done when:

- `ArcaneClient.evaluate(...)` exists
- `POST /api/evals` exists
- the new submission shape is persisted

### Milestone B: Model target is real

Done when:

- provider-backed evals work
- endpoint-backed evals work
- model provenance is persisted on runs

### Milestone C: Control-plane skeleton exists

Done when:

- `PolicyVersion`
- `RolloutGroup`
- `TrainingWindow`
- `TrainingJob`
- `ServingDeployment`

exist and are persisted

### Milestone D: One managed model path exists

Done when:

- one concrete provider backend exists
- one managed `ModelTarget` path works
- one serving backend path works

### Milestone E: RL loop skeleton exists

Done when:

- `DRAINING` works
- training windows can be sealed
- one training backend path works
- new policy version can be registered and promoted

## Frontend / Contract Follow-Up

As soon as the new eval submission and run metadata shapes stabilize, update:

- `scripts/export_contract_schemas.py`
- `arcane-dashboard/scripts/generate-rest-contracts.mjs`
- generated REST contracts
- frontend run state types

This should happen after the new API and persistence model settle enough to avoid churn.

## Things To Delay On Purpose

Do not try to solve these in the first implementation wave:

- multiple provider backends
- multiple serving backends
- multiple training runtimes
- full rollout-worker fleet design
- polished Slurm / k8s / SkyPilot support

You only need one real path first.

## Final Position

The first implementation should focus on:

- the new public eval/model submission surface
- internal control-plane objects
- one concrete provider backend
- one concrete serving backend
- one concrete training path

That is enough to validate the architecture without scattering effort across too many integrations too early.
