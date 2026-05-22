# PRD 10: Application Domain Layout Convention

## Goal

Standardize surviving `core/application/*` domains after the core refactor so
each domain has a clear public surface, private internals, and enforceable
cross-domain import rules.

## Timing

This PRD should be implemented after the current structural stack lands,
especially:

- `implementation-plan/04-views-package-foundation.md`;
- `implementation-plan/08-legacy-experiment-and-cohort-isolation.md`;
- `implementation-plan/10-job-composition-modules.md`;
- `implementation-plan/11-application-runtime-restructure.md`;
- `implementation-plan/12-final-folder-state-and-architecture-gates.md`.

Before those PRs land, the application tree still contains temporary package
roots such as `application/jobs`, `application/read_models`,
`application/graph`, `application/tasks`, and `application/workflows`. This PRD
is not intended to standardize those temporary roots; it standardizes the
post-stack application domains.

## Pattern

Use a lightweight hexagonal/clean-architecture convention without forcing empty
files.

For each substantial domain:

```text
application/<domain>/
  __init__.py
  service.py          # public behavior facade / use cases
  models.py           # command/result DTOs used by behavior
  errors.py           # public domain/application exceptions
  repository.py       # domain-shaped data access, when needed
  policies.py         # pure business decisions, when needed
  mappers.py          # row/DTO transformations, when needed
```

For larger domains, split internals by noun:

```text
application/<domain>/
  service.py
  models.py
  errors.py
  repositories/
    ...
  policies/
    ...
  mappers/
    ...
```

Allowed cross-domain imports:

- `application.<domain>.service`;
- `application.<domain>.models`;
- `application.<domain>.errors`;
- `application.<domain>` only if `__init__.py` intentionally re-exports those
  public symbols;
- domain-specific public modules recorded in the architecture test allowlist.
  For example, `application.evaluation.summary` may be public because views
  need the evaluation summary contract.

Forbidden cross-domain imports:

- `application.<domain>.repository`;
- `application.<domain>.repositories.*`;
- `application.<domain>.policy`;
- `application.<domain>.policies.*`;
- `application.<domain>.mapper`;
- `application.<domain>.mappers.*`;
- `application.<domain>.dto_mapping`;
- `application.<domain>._*`;
- any other module that the domain marks as internal.

The aim is not to make every domain look identical. The aim is to make every
domain's public behavior obvious and to stop other domains from reaching into
private helpers.

## State Tests

Add permanent architecture tests that enforce the convention.

### Public Surface Import Test

Create or extend an architecture test such as:

```text
ergon_core/tests/unit/architecture/test_application_domain_boundaries.py
```

It should parse imports under `ergon_core.core.application.*` and fail when a
module in one domain imports a private module from another domain.

Default allowed imports:

```python
from ergon_core.core.application.evaluation.service import EvaluationService
from ergon_core.core.application.evaluation.models import EvaluationServiceResult
from ergon_core.core.application.evaluation.errors import EvaluationError
```

Domain-specific allowed imports:

```python
from ergon_core.core.application.evaluation.summary import EvaluationSummary
from ergon_core.core.application.evaluation.scoring import EvaluationScoreSummary
```

Example forbidden imports:

```python
from ergon_core.core.application.evaluation.dto_mapping import evaluation_row_to_dto
from ergon_core.core.application.resources.repository import RunResourceRepository
from ergon_core.core.application.runtime.graph_repository import RuntimeGraphRepository
```

Same-domain imports remain allowed. For example,
`application.evaluation.service` may import
`application.evaluation.mappers`.

### Domain Layout Test

Add a test that checks every first-level package under `core/application/`
belongs to one of these categories:

- active domain: `communication`, `context`, `evaluation`, `experiments`,
  `resources`, `runtime`;
- boundary package: `ports`;
- temporary compatibility package: `compat`;
- deleted roots that must not exist:
  `jobs`, `read_models`, `graph`, `tasks`, `workflows`, `events`.

### Internal Module Naming Test

Add a test that treats these names as internal unless imported from the same
domain:

- `repository.py`;
- `repositories/*`;
- `policy.py`;
- `policies/*`;
- `mapper.py`;
- `mappers/*`;
- `dto_mapping.py`;
- `_*.py`.

### Public Facade Test

Add a test that each active domain has a short module-level docstring in
`service.py` describing:

- what use cases this domain owns;
- what invariants it protects;
- which modules are its public surface.

This is deliberately docstring-based because the repeated failure mode in this
codebase is not only wrong imports, but also unclear ownership.

## Temporary Refactor Tests

For each domain refactor, add characterization tests before moving files or
changing imports. These tests can live under:

```text
ergon_core/tests/unit/application_refactor/
```

They are allowed to be deleted after the domain is standardized and covered by
normal domain tests plus the permanent architecture tests. Their job is to keep
the refactor mechanical and state-preserving.

## Domain Sections

### Runtime

#### Current Folder Path And Logic

Current pre-stack logic is spread across:

```text
application/graph/
application/tasks/
application/workflows/
```

These packages collectively own run graph persistence operations, graph
traversal, propagation, ready-task detection, task lifecycle mutation, task
execution rows, task inspection, workflow initialization/finalization, runtime
resource materialization, and CLI/operator mutation helpers. They also contain
duplicate helpers for descendant traversal, ready-event dispatch, and
definition-id lookup.

After implementation-plan PR 11, the current path should become:

```text
application/runtime/
```

with modules such as `graph_repository.py`, `graph_traversal.py`,
`lifecycle.py`, `run_lifecycle.py`, `task_management.py`,
`task_execution.py`, `task_inspection.py`, `task_cleanup.py`,
`task_execution_repository.py`, `resources.py`, `events.py`,
`run_identity.py`, `models.py`, `errors.py`, and `status.py`.

#### Intended Folder Path

```text
application/runtime/
  __init__.py
  service.py
  models.py
  errors.py
  status.py
  repositories/
    graph.py
    task_execution.py
  policies/
    propagation.py
    traversal.py
    invalidation.py
  resources.py
  events.py
  run_identity.py
```

`service.py` should be the public facade for runtime use cases that other
domains need. It can delegate internally to smaller services such as task
management and run lifecycle, but cross-domain callers should not reach into
graph repositories or traversal policies directly.

#### Plan For Getting There

- Keep the PR 11 `application/runtime` consolidation as the first step.
- Introduce `RuntimeService` or a small set of public facade services in
  `runtime/service.py` after duplicated logic is already colocated.
- Move graph and task-execution repositories under `runtime/repositories/`.
- Move pure traversal/propagation/invalidation helpers under
  `runtime/policies/`.
- Keep public command/result DTOs in `runtime/models.py`.
- Keep lifecycle statuses in `runtime/status.py`.
- Replace cross-domain imports of `runtime.graph_repository`,
  `runtime.graph_traversal`, `runtime.task_management`, and
  `runtime.task_execution_repository` with facade calls on
  `runtime.service` unless the caller is still inside `runtime`.

#### Temporary Refactor Test Suite

- Dynamic task spawn preserves task JSON, parent/child edges, dependency edges,
  and ready events.
- Task completion propagation preserves successor status transitions.
- Task failure propagation preserves descendant blocking behavior.
- Restart/refine preserves invalidation and downstream reset behavior.
- Runtime resource materialization returns the same bytes/location metadata as
  before the move.
- Operator unblock and restart still emit the same graph mutations.

Delete these characterization tests after runtime has stable unit coverage
against the public facade and the permanent architecture tests are in place.

### Evaluation

#### Current Folder Path And Logic

```text
application/evaluation/
  errors.py
  models.py
  scoring.py
  service.py
```

After PR 01 this domain should also own:

```text
application/evaluation/summary.py
application/evaluation/dto_mapping.py
```

The domain currently owns evaluator execution orchestration, evaluation result
persistence, score aggregation, summary construction, and dashboard DTO
mapping. Some helper functions live at module top level inside `service.py`,
which makes it tempting for other code to import behavior that should be
private.

#### Intended Folder Path

```text
application/evaluation/
  __init__.py
  service.py
  models.py
  errors.py
  summary.py
  scoring.py
  mappers.py
```

`service.py`, `models.py`, `errors.py`, `summary.py`, and `scoring.py` are
public. `mappers.py` is internal unless a future views PR explicitly makes a
mapping function a public contract.

#### Plan For Getting There

- Move `dto_mapping.py` to `mappers.py` if it is only used within evaluation
  and views can use a service/facade instead.
- Keep `summary.py` public because views and tests need the semantic schema.
- Keep `scoring.py` public if multiple domains use score summaries; otherwise
  make it internal by moving it under `policies/scoring.py`.
- Move top-level helper functions in `service.py` behind either
  `EvaluationService` methods or internal `mappers.py`/`policies.py` helpers.
- Replace cross-domain imports of evaluation internals with imports from
  `evaluation.service`, `evaluation.models`, `evaluation.errors`,
  `evaluation.summary`, or `evaluation.scoring`.

#### Temporary Refactor Test Suite

- Persisted success creates the same `RunTaskEvaluation` row.
- Persisted failure creates the same failure summary.
- Score aggregation produces the same pass/fail/max-score behavior.
- Dashboard/run snapshot evaluation DTOs are byte-for-byte equivalent before
  and after mapper moves.

Delete these once evaluation service, summary, and scoring tests cover the
public behavior.

### Experiments

#### Current Folder Path And Logic

```text
application/experiments/
  definition_writer.py
  errors.py
  handles.py
  launch.py
  models.py
  service.py
```

This domain owns definition persistence, experiment handles, launch/run
creation entry points, and the public `run_experiment(...)` convenience
service. Read-side experiment DTOs move to `views/experiments` in PR 04.
Legacy experiment-record fallback moves to `application/compat` in PR 08.

#### Intended Folder Path

```text
application/experiments/
  __init__.py
  service.py
  models.py
  errors.py
  repositories/
    definitions.py
  launch.py
  handles.py
```

`service.py`, `models.py`, `errors.py`, and `handles.py` are public.
`repositories/*` is internal to the experiments domain. `launch.py` should
either remain public as an explicit launch facade or be merged into
`service.py`; do not leave both as parallel public entry points for the same
operation.

#### Plan For Getting There

- Decide whether `launch_run(...)` is a public use case. If yes, re-export it
  through `experiments/service.py` or `experiments/__init__.py`; if no, make it
  internal to `service.py`.
- Move definition writer persistence helpers into
  `experiments/repositories/definitions.py` if they are data-access shaped.
- Keep command/result DTOs in `experiments/models.py`.
- Keep `DefinitionHandle` in `handles.py` if it remains a public product
  concept; otherwise merge it into `models.py`.
- Remove any direct imports of definition writer internals from other domains.

#### Temporary Refactor Test Suite

- Persisting a benchmark definition writes the same definition rows.
- Launching a run initializes the same runtime graph and emits the same
  workflow-started event.
- Definition handles round-trip through public APIs.
- Legacy experiment fallback remains covered by compat tests until PR 09
  deletes it.

Delete these after experiments has stable definition persistence and launch
service tests.

### Resources

#### Current Folder Path And Logic

```text
application/resources/
  errors.py
  models.py
  repository.py
```

After PR 07 this domain should also own:

```text
application/resources/publishing.py
```

The domain currently owns run resource data access and resource DTOs/errors.
Resource append/dedup semantics are still partly in sandbox infrastructure
until PR 07 moves them into application.

#### Intended Folder Path

```text
application/resources/
  __init__.py
  service.py
  models.py
  errors.py
  repository.py
  publishing.py
```

`service.py`, `models.py`, and `errors.py` are public. `repository.py` and
`publishing.py` are internal unless the public facade deliberately exposes
their operations.

#### Plan For Getting There

- Add `ResourceService` in `resources/service.py` as the public facade for
  resource use cases that other domains need.
- Keep `RunResourceRepository` in `repository.py`, but make cross-domain
  callers go through `ResourceService`.
- Keep `RunResourcePublishService` in `publishing.py`, but treat it as internal
  to the resources domain after PR 07 unless jobs need it as a composition
  boundary.
- Move reusable command/result DTOs to `models.py`; keep view DTOs in
  `views/resources.py`.
- Replace direct imports of `RunResourceRepository` from outside `resources`
  with facade calls.

#### Temporary Refactor Test Suite

- Listing resources by run/execution returns the same rows.
- Latest-by-path and find-by-hash behavior is unchanged.
- Append/dedup semantics match PR 07 characterization tests.
- Resource size visibility checks remain in views or service as decided by the
  implementation.

Delete these once `ResourceService` has normal unit coverage.

### Communication

#### Current Folder Path And Logic

```text
application/communication/
  errors.py
  models.py
  service.py
```

The domain owns communication thread/message creation and read DTOs for
worker/context communication. It is already close to the intended shape, but
its DTOs should be classified: command/result models stay here; dashboard/API
read contracts should move to `views` if they become broader read models.

#### Intended Folder Path

```text
application/communication/
  __init__.py
  service.py
  models.py
  errors.py
```

No repository file is needed unless communication data access becomes reused
outside the service.

#### Plan For Getting There

- Audit `models.py` and classify each DTO as command/result vs view contract.
- Keep create/send command models in `communication/models.py`.
- Move read-only dashboard/API view DTOs to `views` only if they are
  consumed outside communication service boundaries.
- Add a module docstring to `service.py` naming this as the public facade.
- Ensure other domains call `communication.service`, not private helpers.

#### Temporary Refactor Test Suite

- Creating a communication message persists the same thread/message rows.
- Listing thread summaries and messages returns the same shape.
- Error translation remains stable.

Delete these if existing communication tests already cover the same behavior.

### Context

#### Current Folder Path And Logic

```text
application/context/
  events.py
```

This domain owns context event persistence sequencing, turn-id extraction, event
listeners, and read helpers for context events. Shared context payload schemas
move to `core/shared/context_parts.py` in PR 03.

#### Intended Folder Path

```text
application/context/
  __init__.py
  service.py
  models.py
  errors.py
```

If there are no domain-specific command/result DTOs or errors, omit
`models.py` and `errors.py`. `service.py` should replace `events.py` as the
public behavior facade.

#### Plan For Getting There

- Rename `events.py` to `service.py` if `ContextEventService` remains the
  public facade.
- Move any local command/result DTOs to `models.py` only if they exist.
- Keep payload schemas in `core/shared/context_parts.py`.
- Ensure views/dashboard code consumes context read behavior through the public
  service or through `views`, not by importing private helper methods.

#### Temporary Refactor Test Suite

- Persisting chunks creates the same `RunContextEvent` rows and sequence
  numbers.
- Turn-id extraction produces the same values.
- Listener callbacks still receive emitted events.
- `get_for_execution` and `get_for_run` return the same ordering.

Delete these after context service tests cover the public facade.

### Compatibility

#### Current Folder Path And Logic

After PR 08, compatibility logic should live under:

```text
application/compat/
  cohorts.py
  legacy_experiments.py
```

These modules isolate deprecated cohort and legacy experiment-record behavior
until PR 09 deletes it.

#### Intended Folder Path

```text
application/compat/
  __init__.py
  cohorts.py
  legacy_experiments.py
```

This is intentionally not a permanent domain. It has no standard repository or
service layout because every module should carry its own deletion path.

#### Plan For Getting There

- Add module docstrings that name the deleting PR/condition.
- Keep imports of compatibility modules out of normal domains except where the
  PR stack explicitly allows a transitional fallback.
- Delete the package in PR 09 if no compatibility behavior remains.

#### Temporary Refactor Test Suite

- Legacy experiment fallback still works while compatibility exists.
- Cohort compatibility routes and dashboard events still work until deletion.
- Source tests ensure compatibility imports do not spread into new runtime
  services.

Delete the tests with the compatibility package.

### Ports

#### Current Folder Path And Logic

After infrastructure cleanup, application ports should live under:

```text
application/ports/
  dashboard.py
  resources.py
  sandbox.py
```

Ports describe external effects that application services/jobs need without
depending on concrete infrastructure.

#### Intended Folder Path

```text
application/ports/
  __init__.py
  dashboard.py
  resources.py
  sandbox.py
```

Ports are boundary contracts, not a behavior domain. They may be imported by
application services and jobs. Infrastructure implements them.

#### Plan For Getting There

- Keep each port module narrow and named after the external effect.
- Do not put command services, repositories, or DTO mappers in `ports`.
- If a port grows multiple unrelated methods, split it by operation rather than
  creating a broad manager protocol.
- Add tests that concrete infrastructure implementations satisfy the protocol
  structurally where practical.

#### Temporary Refactor Test Suite

- Dashboard publisher implementation emits the same event payload.
- Sandbox/blob/resource adapter protocols are satisfied by concrete
  infrastructure classes.
- Jobs can receive fake port implementations in unit tests.

Keep fake-port tests if they remain useful for job unit tests.

## Acceptance Criteria

- Every active `application/*` domain has a documented public surface.
- Cross-domain imports use only `service.py`, `models.py`, `errors.py`, or
  explicit package re-exports.
- Internal modules such as repositories, policies, and mappers are only
  imported from inside their own domain.
- Temporary characterization tests exist for each domain before its refactor
  starts.
- Characterization tests are deleted or replaced by normal unit tests after
  each domain reaches the target layout.
- Permanent architecture tests enforce the convention after the refactor.

## Non-Goals

- Do not standardize temporary roots that the existing PR stack deletes.
- Do not force empty `repository.py`, `models.py`, or `errors.py` files into
  tiny domains.
- Do not move persistence rows, view DTOs, infrastructure adapters, or job
  contracts into application domains to make the tree look symmetrical.
- Do not treat this PRD as a mandate for one giant PR. Each domain should be
  refactored in its own small PR after the structural stack lands.

## Evidence

- [`../implementation-plan/00-program.md`](../implementation-plan/00-program.md)
- [`09-final-core-folder-state.md`](09-final-core-folder-state.md)
- [`../audits/runtime-domain-merge-audit.md`](../audits/runtime-domain-merge-audit.md)
- [`../audits/current-structure.md`](../audits/current-structure.md)
