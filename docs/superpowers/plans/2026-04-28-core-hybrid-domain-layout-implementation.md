# Core Hybrid Domain Layout Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move `ergon_core.core` to the approved hybrid layout: thin `rest_api`, product use cases under `application`, pure objects under `domain`, adapters under `infrastructure`, SQL rows under `persistence`, and `rl` kept as a separate bounded context.

**Architecture:** This is a mechanical package migration with architecture guards. Each slice moves one cluster, bulk-renames imports, runs focused tests, and preserves behavior. A temporary exact-folder-structure test is added first and deleted at the end after durable architecture tests cover the important constraints.

**Tech Stack:** Python, pytest, ruff, SQLModel, FastAPI, Inngest, Pydantic.

**Commit Policy:** Do not create git commits unless the user explicitly asks. Treat each task's test run as the checkpoint.

---

## Target Clusters

The implementation follows `docs/superpowers/plans/2026-04-28-core-hybrid-domain-layout.md`.

```text
core/
  rest_api/
  application/
    experiments/
    workflows/
    graph/
    tasks/
    evaluation/
    read_models/
    communication/
    context/
    jobs/
    resources/
    events/
  domain/
    experiments/
    generation/
  persistence/
  infrastructure/
    inngest/
      handlers/
    sandbox/
    dashboard/
    tracing/
    dependencies.py
  rl/
  shared/
```

## Task 1: Add Temporary Exact Layout Guard

**Files:**
- Create: `tests/unit/architecture/test_core_hybrid_layout_temporary.py`
- Modify: none
- Test: `tests/unit/architecture/test_core_hybrid_layout_temporary.py`

- [ ] **Step 1: Add the temporary failing test**

Create `tests/unit/architecture/test_core_hybrid_layout_temporary.py`:

```python
"""Temporary guard for the core hybrid layout migration.

Delete this file in the final migration task. It intentionally asserts the
exact file tree so each migration slice has a visible end state.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
CORE = ROOT / "ergon_core/ergon_core/core"

EXPECTED_FILES = {
    "__init__.py",
    "rest_api/__init__.py",
    "rest_api/app.py",
    "rest_api/cohorts.py",
    "rest_api/experiments.py",
    "rest_api/rollouts.py",
    "rest_api/runs.py",
    "rest_api/test_harness.py",
    "application/__init__.py",
    "application/experiments/__init__.py",
    "application/experiments/service.py",
    "application/experiments/models.py",
    "application/experiments/repository.py",
    "application/experiments/definition_writer.py",
    "application/experiments/launch.py",
    "application/workflows/__init__.py",
    "application/workflows/service.py",
    "application/workflows/orchestration.py",
    "application/workflows/runs.py",
    "application/workflows/models.py",
    "application/workflows/errors.py",
    "application/graph/__init__.py",
    "application/graph/repository.py",
    "application/graph/propagation.py",
    "application/graph/traversal.py",
    "application/graph/lookup.py",
    "application/graph/models.py",
    "application/graph/errors.py",
    "application/tasks/__init__.py",
    "application/tasks/service.py",
    "application/tasks/execution.py",
    "application/tasks/management.py",
    "application/tasks/inspection.py",
    "application/tasks/cleanup.py",
    "application/tasks/repository.py",
    "application/tasks/models.py",
    "application/tasks/errors.py",
    "application/evaluation/__init__.py",
    "application/evaluation/service.py",
    "application/evaluation/executors.py",
    "application/evaluation/inngest_executor.py",
    "application/evaluation/criterion_runtime.py",
    "application/evaluation/scoring.py",
    "application/evaluation/protocols.py",
    "application/evaluation/models.py",
    "application/evaluation/errors.py",
    "application/read_models/__init__.py",
    "application/read_models/runs.py",
    "application/read_models/run_snapshot.py",
    "application/read_models/experiments.py",
    "application/read_models/cohorts.py",
    "application/read_models/resources.py",
    "application/read_models/models.py",
    "application/read_models/errors.py",
    "application/communication/__init__.py",
    "application/communication/service.py",
    "application/communication/models.py",
    "application/communication/errors.py",
    "application/context/__init__.py",
    "application/context/events.py",
    "application/context/output_extraction.py",
    "application/jobs/__init__.py",
    "application/jobs/cancel_orphan_subtasks.py",
    "application/jobs/check_evaluators.py",
    "application/jobs/cleanup_cancelled_task.py",
    "application/jobs/complete_workflow.py",
    "application/jobs/evaluate_task_run.py",
    "application/jobs/execute_task.py",
    "application/jobs/fail_workflow.py",
    "application/jobs/persist_outputs.py",
    "application/jobs/propagate_execution.py",
    "application/jobs/run_cleanup.py",
    "application/jobs/sandbox_setup.py",
    "application/jobs/start_workflow.py",
    "application/jobs/worker_execute.py",
    "application/jobs/models.py",
    "application/resources/__init__.py",
    "application/resources/repository.py",
    "application/resources/models.py",
    "application/events/__init__.py",
    "application/events/base.py",
    "application/events/task_events.py",
    "application/events/infrastructure_events.py",
    "domain/__init__.py",
    "domain/experiments/__init__.py",
    "domain/experiments/experiment.py",
    "domain/experiments/handles.py",
    "domain/experiments/worker_spec.py",
    "domain/experiments/validation.py",
    "domain/generation/__init__.py",
    "domain/generation/context_parts.py",
    "persistence/shared/__init__.py",
    "persistence/shared/db.py",
    "persistence/shared/enums.py",
    "persistence/shared/ids.py",
    "persistence/shared/types.py",
    "persistence/definitions/__init__.py",
    "persistence/definitions/models.py",
    "persistence/telemetry/__init__.py",
    "persistence/telemetry/models.py",
    "persistence/telemetry/repositories.py",
    "persistence/telemetry/evaluation_summary.py",
    "persistence/graph/__init__.py",
    "persistence/graph/models.py",
    "persistence/graph/status_conventions.py",
    "persistence/context/__init__.py",
    "persistence/context/models.py",
    "persistence/context/event_payloads.py",
    "persistence/saved_specs/__init__.py",
    "persistence/saved_specs/models.py",
    "infrastructure/__init__.py",
    "infrastructure/inngest/__init__.py",
    "infrastructure/inngest/client.py",
    "infrastructure/inngest/registry.py",
    "infrastructure/inngest/contracts.py",
    "infrastructure/inngest/errors.py",
    "infrastructure/inngest/handlers/__init__.py",
    "infrastructure/inngest/handlers/cancel_orphan_subtasks.py",
    "infrastructure/inngest/handlers/check_evaluators.py",
    "infrastructure/inngest/handlers/cleanup_cancelled_task.py",
    "infrastructure/inngest/handlers/complete_workflow.py",
    "infrastructure/inngest/handlers/evaluate_task_run.py",
    "infrastructure/inngest/handlers/execute_task.py",
    "infrastructure/inngest/handlers/fail_workflow.py",
    "infrastructure/inngest/handlers/persist_outputs.py",
    "infrastructure/inngest/handlers/propagate_execution.py",
    "infrastructure/inngest/handlers/run_cleanup.py",
    "infrastructure/inngest/handlers/sandbox_setup.py",
    "infrastructure/inngest/handlers/start_workflow.py",
    "infrastructure/inngest/handlers/worker_execute.py",
    "infrastructure/sandbox/__init__.py",
    "infrastructure/sandbox/manager.py",
    "infrastructure/sandbox/lifecycle.py",
    "infrastructure/sandbox/resource_publisher.py",
    "infrastructure/sandbox/instrumentation.py",
    "infrastructure/sandbox/event_sink.py",
    "infrastructure/sandbox/errors.py",
    "infrastructure/sandbox/utils.py",
    "infrastructure/dashboard/__init__.py",
    "infrastructure/dashboard/emitter.py",
    "infrastructure/dashboard/provider.py",
    "infrastructure/dashboard/event_contracts.py",
    "infrastructure/tracing/__init__.py",
    "infrastructure/tracing/attributes.py",
    "infrastructure/tracing/contexts.py",
    "infrastructure/tracing/ids.py",
    "infrastructure/tracing/noop.py",
    "infrastructure/tracing/otel.py",
    "infrastructure/tracing/sinks.py",
    "infrastructure/tracing/types.py",
    "infrastructure/dependencies.py",
    "rl/__init__.py",
    "rl/rollout_service.py",
    "rl/eval_runner.py",
    "rl/extraction.py",
    "rl/rewards.py",
    "rl/checkpoint.py",
    "rl/rollout_types.py",
    "rl/vllm_manager.py",
    "shared/__init__.py",
    "shared/json_types.py",
    "shared/settings.py",
    "shared/utils.py",
}

REMOVED_DIRS = {
    "api",
    "definitions",
    "composition",
    "runtime",
    "sandbox",
    "dashboard",
}

REMOVED_ROOT_FILES = {
    "generation.py",
    "json_types.py",
    "settings.py",
    "utils.py",
}


def test_core_has_exact_target_layout_during_migration() -> None:
    actual_files = {
        str(path.relative_to(CORE))
        for path in CORE.rglob("*.py")
        if "__pycache__" not in path.parts
    }
    missing = sorted(EXPECTED_FILES - actual_files)
    unexpected = sorted(actual_files - EXPECTED_FILES)

    assert missing == []
    assert unexpected == []


def test_old_core_roots_are_removed_during_migration() -> None:
    restored_dirs = sorted(name for name in REMOVED_DIRS if (CORE / name).exists())
    restored_files = sorted(name for name in REMOVED_ROOT_FILES if (CORE / name).exists())

    assert restored_dirs == []
    assert restored_files == []
```

- [ ] **Step 2: Run the temporary test and confirm it fails**

Run:

```bash
uv run pytest tests/unit/architecture/test_core_hybrid_layout_temporary.py -q
```

Expected: FAIL because the target directories do not exist yet and old roots still exist.

## Task 2: Rename HTTP Layer To `core/rest_api`

**Files:**
- Move: `ergon_core/ergon_core/core/api/*` -> `ergon_core/ergon_core/core/rest_api/*`
- Modify: imports in `ergon_core/ergon_core/core/rest_api/*.py`
- Modify: imports across `ergon_core`, `ergon_cli`, `ergon_builtins`, and `tests`
- Test: `tests/unit/architecture/test_public_api_boundaries.py`
- Test: `tests/unit/architecture/test_core_schema_sources.py`

- [ ] **Step 1: Move the package**

Move files:

```bash
mkdir -p ergon_core/ergon_core/core/rest_api
mv ergon_core/ergon_core/core/api/*.py ergon_core/ergon_core/core/rest_api/
rmdir ergon_core/ergon_core/core/api
```

- [ ] **Step 2: Bulk update imports**

Replace every `ergon_core.core.api` import with `ergon_core.core.rest_api`.

Run:

```bash
python - <<'PY'
from pathlib import Path

for root in [Path("ergon_core"), Path("ergon_cli"), Path("ergon_builtins"), Path("tests")]:
    for path in root.rglob("*.py"):
        text = path.read_text()
        new = text.replace("ergon_core.core.api", "ergon_core.core.rest_api")
        if new != text:
            path.write_text(new)
PY
```

- [ ] **Step 3: Add a durable architecture guard**

In `tests/unit/architecture/test_public_api_boundaries.py`, add:

```python
def test_internal_http_api_is_named_rest_api_not_core_api() -> None:
    core_root = ROOT / "ergon_core" / "ergon_core" / "core"

    assert not (core_root / "api").exists()
    assert (core_root / "rest_api").exists()
```

- [ ] **Step 4: Run focused tests**

Run:

```bash
uv run pytest tests/unit/architecture/test_public_api_boundaries.py tests/unit/architecture/test_core_schema_sources.py -q
```

Expected: PASS for durable architecture tests. The temporary exact-layout test still fails until the full migration finishes.

## Task 3: Move Shared Primitives And Pure Domain Objects

**Files:**
- Move: `core/json_types.py` -> `core/shared/json_types.py`
- Move: `core/settings.py` -> `core/shared/settings.py`
- Move: `core/utils.py` -> `core/shared/utils.py`
- Move: `core/generation.py` -> `core/domain/generation/context_parts.py`
- Move: `core/composition/*` -> `core/domain/experiments/*`
- Create: `core/shared/__init__.py`
- Create: `core/domain/__init__.py`
- Create: `core/domain/generation/__init__.py`
- Modify: imports across source and tests
- Test: `tests/unit/architecture/test_public_api_boundaries.py`
- Test: `tests/unit/architecture/test_core_schema_sources.py`

- [ ] **Step 1: Move shared files**

Run:

```bash
mkdir -p ergon_core/ergon_core/core/shared
mv ergon_core/ergon_core/core/json_types.py ergon_core/ergon_core/core/shared/json_types.py
mv ergon_core/ergon_core/core/settings.py ergon_core/ergon_core/core/shared/settings.py
mv ergon_core/ergon_core/core/utils.py ergon_core/ergon_core/core/shared/utils.py
touch ergon_core/ergon_core/core/shared/__init__.py
```

- [ ] **Step 2: Move generation primitives**

Run:

```bash
mkdir -p ergon_core/ergon_core/core/domain/generation
mv ergon_core/ergon_core/core/generation.py ergon_core/ergon_core/core/domain/generation/context_parts.py
touch ergon_core/ergon_core/core/domain/__init__.py
touch ergon_core/ergon_core/core/domain/generation/__init__.py
```

- [ ] **Step 3: Move experiment composition domain**

Run:

```bash
mkdir -p ergon_core/ergon_core/core/domain/experiments
mv ergon_core/ergon_core/core/composition/*.py ergon_core/ergon_core/core/domain/experiments/
rmdir ergon_core/ergon_core/core/composition
```

- [ ] **Step 4: Bulk update imports**

Run:

```bash
python - <<'PY'
from pathlib import Path

replacements = {
    "ergon_core.core.json_types": "ergon_core.core.shared.json_types",
    "ergon_core.core.settings": "ergon_core.core.shared.settings",
    "ergon_core.core.utils": "ergon_core.core.shared.utils",
    "ergon_core.core.generation": "ergon_core.core.domain.generation.context_parts",
    "ergon_core.core.composition": "ergon_core.core.domain.experiments",
}

for root in [Path("ergon_core"), Path("ergon_cli"), Path("ergon_builtins"), Path("tests")]:
    for path in root.rglob("*.py"):
        text = path.read_text()
        new = text
        for old, replacement in replacements.items():
            new = new.replace(old, replacement)
        if new != text:
            path.write_text(new)
PY
```

- [ ] **Step 5: Restore domain exports**

Ensure `ergon_core/ergon_core/core/domain/experiments/__init__.py` exports the same names previously exported by `core/composition/__init__.py`:

```python
from ergon_core.core.domain.experiments.experiment import Experiment
from ergon_core.core.domain.experiments.handles import DefinitionHandle
from ergon_core.core.domain.experiments.worker_spec import WorkerSpec

__all__ = ["DefinitionHandle", "Experiment", "WorkerSpec"]
```

- [ ] **Step 6: Run focused tests**

Run:

```bash
uv run pytest tests/unit/architecture/test_public_api_boundaries.py tests/unit/architecture/test_core_schema_sources.py tests/unit/api/test_public_api_imports.py -q
```

Expected: PASS.

## Task 4: Move Experiment Application Cluster

**Files:**
- Move: `core/definitions/service.py` -> `core/application/experiments/service.py`
- Move: `core/definitions/schemas.py` -> `core/application/experiments/models.py`
- Move: `core/definitions/repository.py` -> `core/application/experiments/repository.py`
- Move: `core/definitions/persistence.py` -> `core/application/experiments/definition_writer.py`
- Move: `core/runtime/workflows/launch.py` -> `core/application/experiments/launch.py`
- Create: `core/application/__init__.py`
- Create: `core/application/experiments/__init__.py`
- Delete: `core/definitions/`
- Test: `tests/unit/runtime/test_experiment_definition_service.py`
- Test: `tests/unit/runtime/test_experiment_launch_service.py`
- Test: `tests/unit/cli/test_experiment_cli.py`

- [ ] **Step 1: Move files**

Run:

```bash
mkdir -p ergon_core/ergon_core/core/application/experiments
mv ergon_core/ergon_core/core/definitions/service.py ergon_core/ergon_core/core/application/experiments/service.py
mv ergon_core/ergon_core/core/definitions/schemas.py ergon_core/ergon_core/core/application/experiments/models.py
mv ergon_core/ergon_core/core/definitions/repository.py ergon_core/ergon_core/core/application/experiments/repository.py
mv ergon_core/ergon_core/core/definitions/persistence.py ergon_core/ergon_core/core/application/experiments/definition_writer.py
mv ergon_core/ergon_core/core/runtime/workflows/launch.py ergon_core/ergon_core/core/application/experiments/launch.py
touch ergon_core/ergon_core/core/application/__init__.py
touch ergon_core/ergon_core/core/application/experiments/__init__.py
rm ergon_core/ergon_core/core/definitions/__init__.py
rmdir ergon_core/ergon_core/core/definitions
```

- [ ] **Step 2: Bulk update imports**

Run:

```bash
python - <<'PY'
from pathlib import Path

replacements = {
    "ergon_core.core.definitions.service": "ergon_core.core.application.experiments.service",
    "ergon_core.core.definitions.schemas": "ergon_core.core.application.experiments.models",
    "ergon_core.core.definitions.repository": "ergon_core.core.application.experiments.repository",
    "ergon_core.core.definitions.persistence": "ergon_core.core.application.experiments.definition_writer",
    "ergon_core.core.runtime.workflows.launch": "ergon_core.core.application.experiments.launch",
}

for root in [Path("ergon_core"), Path("ergon_cli"), Path("ergon_builtins"), Path("tests")]:
    for path in root.rglob("*.py"):
        text = path.read_text()
        new = text
        for old, replacement in replacements.items():
            new = new.replace(old, replacement)
        if new != text:
            path.write_text(new)
PY
```

- [ ] **Step 3: Ensure experiment package exports the front door**

Set `ergon_core/ergon_core/core/application/experiments/__init__.py` to:

```python
from ergon_core.core.application.experiments.service import ExperimentService

__all__ = ["ExperimentService"]
```

- [ ] **Step 4: Run focused tests**

Run:

```bash
uv run pytest tests/unit/runtime/test_experiment_definition_service.py tests/unit/runtime/test_experiment_launch_service.py tests/unit/cli/test_experiment_cli.py -q
```

Expected: PASS.

## Task 5: Move Workflow, Graph, Task, And Evaluation Application Clusters

**Files:**
- Move: `core/runtime/workflows/{service,orchestration,runs,models,errors}.py` -> `core/application/workflows/`
- Move: `core/runtime/graph/{repository,propagation,traversal,lookup,dto,errors}.py` -> `core/application/graph/`
- Rename: `core/application/graph/dto.py` -> `core/application/graph/models.py`
- Move: `core/runtime/tasks/*` -> `core/application/tasks/`
- Rename: `core/application/tasks/management.py` remains `management.py`
- Create: `core/application/tasks/service.py` if needed as a package front door
- Move: `core/runtime/evaluation/*` -> `core/application/evaluation/`
- Modify: imports across source and tests
- Test: runtime workflow/task/evaluation tests

- [ ] **Step 1: Move workflows**

Run:

```bash
mkdir -p ergon_core/ergon_core/core/application/workflows
mv ergon_core/ergon_core/core/runtime/workflows/service.py ergon_core/ergon_core/core/application/workflows/service.py
mv ergon_core/ergon_core/core/runtime/workflows/orchestration.py ergon_core/ergon_core/core/application/workflows/orchestration.py
mv ergon_core/ergon_core/core/runtime/workflows/runs.py ergon_core/ergon_core/core/application/workflows/runs.py
mv ergon_core/ergon_core/core/runtime/workflows/models.py ergon_core/ergon_core/core/application/workflows/models.py
mv ergon_core/ergon_core/core/runtime/workflows/errors.py ergon_core/ergon_core/core/application/workflows/errors.py
touch ergon_core/ergon_core/core/application/workflows/__init__.py
rm -f ergon_core/ergon_core/core/runtime/workflows/__init__.py
rmdir ergon_core/ergon_core/core/runtime/workflows
```

- [ ] **Step 2: Move graph**

Run:

```bash
mkdir -p ergon_core/ergon_core/core/application/graph
mv ergon_core/ergon_core/core/runtime/graph/repository.py ergon_core/ergon_core/core/application/graph/repository.py
mv ergon_core/ergon_core/core/runtime/graph/propagation.py ergon_core/ergon_core/core/application/graph/propagation.py
mv ergon_core/ergon_core/core/runtime/graph/traversal.py ergon_core/ergon_core/core/application/graph/traversal.py
mv ergon_core/ergon_core/core/runtime/graph/lookup.py ergon_core/ergon_core/core/application/graph/lookup.py
mv ergon_core/ergon_core/core/runtime/graph/dto.py ergon_core/ergon_core/core/application/graph/models.py
mv ergon_core/ergon_core/core/runtime/graph/errors.py ergon_core/ergon_core/core/application/graph/errors.py
touch ergon_core/ergon_core/core/application/graph/__init__.py
rm -f ergon_core/ergon_core/core/runtime/graph/__init__.py
rmdir ergon_core/ergon_core/core/runtime/graph
```

- [ ] **Step 3: Move tasks**

Run:

```bash
mkdir -p ergon_core/ergon_core/core/application/tasks
mv ergon_core/ergon_core/core/runtime/tasks/*.py ergon_core/ergon_core/core/application/tasks/
touch ergon_core/ergon_core/core/application/tasks/service.py
rmdir ergon_core/ergon_core/core/runtime/tasks
```

Set `ergon_core/ergon_core/core/application/tasks/service.py` to:

```python
"""Task application package front door.

Task lifecycle behavior currently lives in focused modules:
`execution`, `management`, `inspection`, and `cleanup`.
"""

from ergon_core.core.application.tasks.execution import TaskExecutionService
from ergon_core.core.application.tasks.management import TaskManagementService

__all__ = ["TaskExecutionService", "TaskManagementService"]
```

- [ ] **Step 4: Move evaluation**

Run:

```bash
mkdir -p ergon_core/ergon_core/core/application/evaluation
mv ergon_core/ergon_core/core/runtime/evaluation/*.py ergon_core/ergon_core/core/application/evaluation/
touch ergon_core/ergon_core/core/application/evaluation/__init__.py
rmdir ergon_core/ergon_core/core/runtime/evaluation
```

- [ ] **Step 5: Bulk update imports**

Run:

```bash
python - <<'PY'
from pathlib import Path

replacements = {
    "ergon_core.core.runtime.workflows": "ergon_core.core.application.workflows",
    "ergon_core.core.runtime.graph.dto": "ergon_core.core.application.graph.models",
    "ergon_core.core.runtime.graph": "ergon_core.core.application.graph",
    "ergon_core.core.runtime.tasks": "ergon_core.core.application.tasks",
    "ergon_core.core.runtime.evaluation": "ergon_core.core.application.evaluation",
}

for root in [Path("ergon_core"), Path("ergon_cli"), Path("ergon_builtins"), Path("tests")]:
    for path in root.rglob("*.py"):
        text = path.read_text()
        new = text
        for old, replacement in replacements.items():
            new = new.replace(old, replacement)
        if new != text:
            path.write_text(new)
PY
```

- [ ] **Step 6: Run focused tests**

Run:

```bash
uv run pytest tests/unit/runtime/test_workflow_service.py tests/unit/runtime/test_graph_mutation_contracts.py tests/unit/runtime/test_graph_worker_identity.py tests/unit/runtime/test_task_execution_repository.py tests/unit/runtime/test_inngest_criterion_executor.py tests/unit/runtime/test_dynamic_task_evaluation_mapping.py -q
```

Expected: PASS.

## Task 6: Move Read Models, Communication, Context, And Resources

**Files:**
- Move: `core/runtime/read_models/{runs,run_snapshot,experiments,cohorts,resources,errors}.py` -> `core/application/read_models/`
- Split: communication DTOs from `read_models/models.py` -> `core/application/communication/models.py`
- Move: `core/runtime/read_models/communication.py` -> `core/application/communication/service.py`
- Move: remaining read model DTOs -> `core/application/read_models/models.py`
- Move: `core/runtime/context_events.py` -> `core/application/context/events.py`
- Move: `core/runtime/output_extraction.py` -> `core/application/context/output_extraction.py`
- Split: `core/runtime/resources.py` -> `core/application/resources/models.py` and `core/application/resources/repository.py`
- Test: dashboard/read-model/context/resource tests

- [ ] **Step 1: Move read models**

Run:

```bash
mkdir -p ergon_core/ergon_core/core/application/read_models
mv ergon_core/ergon_core/core/runtime/read_models/runs.py ergon_core/ergon_core/core/application/read_models/runs.py
mv ergon_core/ergon_core/core/runtime/read_models/run_snapshot.py ergon_core/ergon_core/core/application/read_models/run_snapshot.py
mv ergon_core/ergon_core/core/runtime/read_models/experiments.py ergon_core/ergon_core/core/application/read_models/experiments.py
mv ergon_core/ergon_core/core/runtime/read_models/cohorts.py ergon_core/ergon_core/core/application/read_models/cohorts.py
mv ergon_core/ergon_core/core/runtime/read_models/resources.py ergon_core/ergon_core/core/application/read_models/resources.py
mv ergon_core/ergon_core/core/runtime/read_models/errors.py ergon_core/ergon_core/core/application/read_models/errors.py
mv ergon_core/ergon_core/core/runtime/read_models/models.py ergon_core/ergon_core/core/application/read_models/models.py
touch ergon_core/ergon_core/core/application/read_models/__init__.py
```

- [ ] **Step 2: Move communication domain**

Run:

```bash
mkdir -p ergon_core/ergon_core/core/application/communication
mv ergon_core/ergon_core/core/runtime/read_models/communication.py ergon_core/ergon_core/core/application/communication/service.py
touch ergon_core/ergon_core/core/application/communication/__init__.py
touch ergon_core/ergon_core/core/application/communication/errors.py
touch ergon_core/ergon_core/core/application/communication/models.py
rm ergon_core/ergon_core/core/runtime/read_models/__init__.py
rmdir ergon_core/ergon_core/core/runtime/read_models
```

Move `RunCommunicationMessageDto` and `RunCommunicationThreadDto` from `application/read_models/models.py` into `application/communication/models.py`, then update imports to read from `ergon_core.core.application.communication.models`.

- [ ] **Step 3: Move context domain**

Run:

```bash
mkdir -p ergon_core/ergon_core/core/application/context
mv ergon_core/ergon_core/core/runtime/context_events.py ergon_core/ergon_core/core/application/context/events.py
mv ergon_core/ergon_core/core/runtime/output_extraction.py ergon_core/ergon_core/core/application/context/output_extraction.py
touch ergon_core/ergon_core/core/application/context/__init__.py
```

- [ ] **Step 4: Split resources module**

Create `ergon_core/ergon_core/core/application/resources/models.py` with `RunResourceView`.

Create `ergon_core/ergon_core/core/application/resources/repository.py` with `RunResourceRepository`.

Delete `ergon_core/ergon_core/core/runtime/resources.py`.

Use this package initializer:

```python
from ergon_core.core.application.resources.models import RunResourceView
from ergon_core.core.application.resources.repository import RunResourceRepository

__all__ = ["RunResourceRepository", "RunResourceView"]
```

- [ ] **Step 5: Bulk update imports**

Run:

```bash
python - <<'PY'
from pathlib import Path

replacements = {
    "ergon_core.core.runtime.read_models.communication": "ergon_core.core.application.communication.service",
    "ergon_core.core.runtime.read_models": "ergon_core.core.application.read_models",
    "ergon_core.core.runtime.context_events": "ergon_core.core.application.context.events",
    "ergon_core.core.runtime.output_extraction": "ergon_core.core.application.context.output_extraction",
    "ergon_core.core.runtime.resources": "ergon_core.core.application.resources",
}

for root in [Path("ergon_core"), Path("ergon_cli"), Path("ergon_builtins"), Path("tests")]:
    for path in root.rglob("*.py"):
        text = path.read_text()
        new = text
        for old, replacement in replacements.items():
            new = new.replace(old, replacement)
        if new != text:
            path.write_text(new)
PY
```

- [ ] **Step 6: Run focused tests**

Run:

```bash
uv run pytest tests/unit/dashboard/test_communication_threads.py tests/unit/runtime/test_communication_service.py tests/unit/persistence/test_context_event_repository.py tests/unit/runtime/test_persist_outputs_resources.py tests/unit/runtime/test_experiment_read_service.py tests/unit/runtime/test_cohort_service.py -q
```

Expected: PASS.

## Task 7: Split Inngest Handlers Into Application Jobs And Infrastructure Adapters

**Files:**
- Move semantic logic: `core/runtime/inngest/{handler files}.py` -> `core/application/jobs/{handler files}.py`
- Create: `core/application/jobs/models.py`
- Create thin adapters: `core/infrastructure/inngest/handlers/{handler files}.py`
- Move: `runtime/inngest/client.py` -> `infrastructure/inngest/client.py`
- Move: `runtime/inngest/registry.py` -> `infrastructure/inngest/registry.py`
- Move: `runtime/inngest/contracts.py` -> `infrastructure/inngest/contracts.py`
- Move: `runtime/inngest/errors.py` -> `infrastructure/inngest/errors.py`
- Test: Inngest/runtime unit tests and import registry tests

- [ ] **Step 1: Move infrastructure primitives**

Run:

```bash
mkdir -p ergon_core/ergon_core/core/infrastructure/inngest/handlers
mv ergon_core/ergon_core/core/runtime/inngest/client.py ergon_core/ergon_core/core/infrastructure/inngest/client.py
mv ergon_core/ergon_core/core/runtime/inngest/registry.py ergon_core/ergon_core/core/infrastructure/inngest/registry.py
mv ergon_core/ergon_core/core/runtime/inngest/contracts.py ergon_core/ergon_core/core/infrastructure/inngest/contracts.py
mv ergon_core/ergon_core/core/runtime/inngest/errors.py ergon_core/ergon_core/core/infrastructure/inngest/errors.py
touch ergon_core/ergon_core/core/infrastructure/__init__.py
touch ergon_core/ergon_core/core/infrastructure/inngest/__init__.py
touch ergon_core/ergon_core/core/infrastructure/inngest/handlers/__init__.py
```

- [ ] **Step 2: Move handler semantics into jobs**

Run:

```bash
mkdir -p ergon_core/ergon_core/core/application/jobs
for name in cancel_orphan_subtasks check_evaluators cleanup_cancelled_task complete_workflow evaluate_task_run execute_task fail_workflow persist_outputs propagate_execution run_cleanup sandbox_setup start_workflow worker_execute; do
  mv "ergon_core/ergon_core/core/runtime/inngest/${name}.py" "ergon_core/ergon_core/core/application/jobs/${name}.py"
done
touch ergon_core/ergon_core/core/application/jobs/__init__.py
rm ergon_core/ergon_core/core/runtime/inngest/__init__.py 2>/dev/null || true
rmdir ergon_core/ergon_core/core/runtime/inngest
```

- [ ] **Step 3: Add thin adapters**

For each moved job, remove the Inngest decorator from the application job file and expose an async `run_<name>_job(...)` function that contains the semantic behavior. The infrastructure handler owns the `@inngest_client.create_function(...)` decorator and delegates to the application job.

For `worker_execute`, transform `core/application/jobs/worker_execute.py` so it starts like this:

```python
"""Application job for worker execution."""

import logging
import traceback
from datetime import UTC, datetime

from ergon_core.api.benchmark import EmptyTaskPayload, Task
from ergon_core.api.worker import WorkerContext
from ergon_core.core.application.context.events import ContextEventService
from ergon_core.core.application.experiments.repository import DefinitionRepository
from ergon_core.core.application.jobs.models import WorkerExecuteJobRequest
from ergon_core.core.application.jobs.models import WorkerExecuteJobResult
from ergon_core.core.domain.generation.context_parts import ContextPartChunk
from ergon_core.core.infrastructure.dashboard.provider import get_dashboard_emitter
from ergon_core.core.persistence.shared.db import get_session
from ergon_core.core.infrastructure.inngest.errors import RegistryLookupError
from ergon_core.core.infrastructure.tracing import (
    CompletedSpan,
    get_trace_sink,
    worker_execute_context,
)
from pydantic import BaseModel

logger = logging.getLogger(__name__)


async def run_worker_execute_job(payload: WorkerExecuteJobRequest) -> WorkerExecuteJobResult:
    from ergon_builtins.registry import BENCHMARKS, WORKERS

    # Move the current body of worker_execute_fn here, replacing ctx.event.data
    # with the typed payload argument.
```

Create `core/application/jobs/models.py` for job request/result aliases imported from Inngest contracts during the first migration:

```python
"""Application job contracts.

These mirror external Inngest event contracts during the migration so job logic
can be called independently of Inngest decorators.
"""

from ergon_core.core.infrastructure.inngest.contracts import (
    CleanupCancelledTaskRequest,
    CleanupCancelledTaskResult,
    CompleteWorkflowRequest,
    CompleteWorkflowResult,
    EvaluateTaskRequest,
    EvaluateTaskResult,
    ExecuteTaskRequest,
    ExecuteTaskResult,
    PropagateExecutionRequest,
    PropagateExecutionResult,
    SandboxSetupRequest,
    SandboxSetupResult,
    StartWorkflowRequest,
    StartWorkflowResult,
    WorkerExecuteRequest as WorkerExecuteJobRequest,
    WorkerExecuteResult as WorkerExecuteJobResult,
)

__all__ = [
    "CleanupCancelledTaskRequest",
    "CleanupCancelledTaskResult",
    "CompleteWorkflowRequest",
    "CompleteWorkflowResult",
    "EvaluateTaskRequest",
    "EvaluateTaskResult",
    "ExecuteTaskRequest",
    "ExecuteTaskResult",
    "PropagateExecutionRequest",
    "PropagateExecutionResult",
    "SandboxSetupRequest",
    "SandboxSetupResult",
    "StartWorkflowRequest",
    "StartWorkflowResult",
    "WorkerExecuteJobRequest",
    "WorkerExecuteJobResult",
]
```

Create `core/infrastructure/inngest/handlers/worker_execute.py` as the thin adapter:

```python
"""Inngest adapter for worker execution."""

import inngest

from ergon_core.core.application.jobs.worker_execute import run_worker_execute_job
from ergon_core.core.infrastructure.inngest.client import inngest_client
from ergon_core.core.infrastructure.inngest.contracts import (
    WorkerExecuteRequest,
    WorkerExecuteResult,
)


@inngest_client.create_function(
    fn_id="worker-execute",
    trigger=inngest.TriggerEvent(event="task/worker-execute"),
    retries=0,
    output_type=WorkerExecuteResult,
)
async def worker_execute_fn(ctx: inngest.Context) -> WorkerExecuteResult:
    return await run_worker_execute_job(WorkerExecuteRequest.model_validate(ctx.event.data))

__all__ = ["worker_execute_fn"]
```

Use the same pattern for every handler: `application/jobs/<name>.py` exports `run_<name>_job`, and `infrastructure/inngest/handlers/<name>.py` owns the decorator and event parsing. Preserve the existing `fn_id`, trigger event, retry policy, and output type from the original handler.

- [ ] **Step 4: Update registry imports**

In `core/infrastructure/inngest/registry.py`, import handler modules from `ergon_core.core.infrastructure.inngest.handlers`.

If the registry currently imports function objects from handler modules, keep the same object names and only change module paths.

- [ ] **Step 5: Bulk update imports**

Run:

```bash
python - <<'PY'
from pathlib import Path

replacements = {
    "ergon_core.core.runtime.inngest.client": "ergon_core.core.infrastructure.inngest.client",
    "ergon_core.core.runtime.inngest.registry": "ergon_core.core.infrastructure.inngest.registry",
    "ergon_core.core.runtime.inngest.contracts": "ergon_core.core.infrastructure.inngest.contracts",
    "ergon_core.core.runtime.inngest.errors": "ergon_core.core.infrastructure.inngest.errors",
    "ergon_core.core.runtime.inngest.": "ergon_core.core.application.jobs.",
}

for root in [Path("ergon_core"), Path("ergon_cli"), Path("ergon_builtins"), Path("tests")]:
    for path in root.rglob("*.py"):
        text = path.read_text()
        new = text
        for old, replacement in replacements.items():
            new = new.replace(old, replacement)
        if new != text:
            path.write_text(new)
PY
```

After the script, inspect `core/infrastructure/inngest/registry.py` and adapter files. Registry imports should point to `infrastructure.inngest.handlers`, not `application.jobs`.

- [ ] **Step 6: Run focused tests**

Run:

```bash
uv run pytest tests/unit/runtime/test_child_function_payloads.py tests/unit/runtime/test_inngest_criterion_executor.py tests/unit/runtime/test_import_boundaries.py tests/unit/registry/test_react_factories.py -q
```

Expected: PASS.

## Task 8: Move Infrastructure Packages

**Files:**
- Move: `core/sandbox/*` -> `core/infrastructure/sandbox/*`
- Move: `core/dashboard/*` -> `core/infrastructure/dashboard/*`
- Move: `core/runtime/tracing/*` -> `core/infrastructure/tracing/*`
- Move: `core/runtime/dependencies.py` -> `core/infrastructure/dependencies.py`
- Modify: imports across source and tests
- Test: dashboard, sandbox, tracing, dependency tests

- [ ] **Step 1: Move sandbox**

Run:

```bash
mkdir -p ergon_core/ergon_core/core/infrastructure/sandbox
mv ergon_core/ergon_core/core/sandbox/*.py ergon_core/ergon_core/core/infrastructure/sandbox/
rmdir ergon_core/ergon_core/core/sandbox
```

- [ ] **Step 2: Move dashboard**

Run:

```bash
mkdir -p ergon_core/ergon_core/core/infrastructure/dashboard
mv ergon_core/ergon_core/core/dashboard/*.py ergon_core/ergon_core/core/infrastructure/dashboard/
rmdir ergon_core/ergon_core/core/dashboard
```

- [ ] **Step 3: Move tracing and dependency probe**

Run:

```bash
mkdir -p ergon_core/ergon_core/core/infrastructure/tracing
mv ergon_core/ergon_core/core/runtime/tracing/*.py ergon_core/ergon_core/core/infrastructure/tracing/
rmdir ergon_core/ergon_core/core/runtime/tracing
mv ergon_core/ergon_core/core/runtime/dependencies.py ergon_core/ergon_core/core/infrastructure/dependencies.py
```

- [ ] **Step 4: Bulk update imports**

Run:

```bash
python - <<'PY'
from pathlib import Path

replacements = {
    "ergon_core.core.sandbox": "ergon_core.core.infrastructure.sandbox",
    "ergon_core.core.dashboard": "ergon_core.core.infrastructure.dashboard",
    "ergon_core.core.runtime.tracing": "ergon_core.core.infrastructure.tracing",
    "ergon_core.core.runtime.dependencies": "ergon_core.core.infrastructure.dependencies",
}

for root in [Path("ergon_core"), Path("ergon_cli"), Path("ergon_builtins"), Path("tests")]:
    for path in root.rglob("*.py"):
        text = path.read_text()
        new = text
        for old, replacement in replacements.items():
            new = new.replace(old, replacement)
        if new != text:
            path.write_text(new)
PY
```

- [ ] **Step 5: Run focused tests**

Run:

```bash
uv run pytest tests/unit/dashboard/test_event_contract_types.py tests/unit/runtime/test_sandbox_setup_explicit_slug.py tests/unit/benchmarks/test_swebench_sandbox_manager.py tests/unit/state/test_benchmark_contract.py -q
```

Expected: PASS.

## Task 9: Move Application Events, Remove Runtime Root, And Add Durable Import Direction Guards

**Files:**
- Move: `ergon_core/ergon_core/core/runtime/events/*` -> `ergon_core/ergon_core/core/application/events/*`
- Delete: `ergon_core/ergon_core/core/runtime/`
- Modify: `tests/unit/architecture/test_core_schema_sources.py`
- Test: architecture suite

- [ ] **Step 1: Delete empty runtime root**

First move the remaining semantic event contracts out of runtime:

```bash
mkdir -p ergon_core/ergon_core/core/application/events
mv ergon_core/ergon_core/core/runtime/events/*.py ergon_core/ergon_core/core/application/events/
rmdir ergon_core/ergon_core/core/runtime/events
```

Then update imports:

```bash
python - <<'PY'
from pathlib import Path

for root in [Path("ergon_core"), Path("ergon_cli"), Path("ergon_builtins"), Path("tests")]:
    for path in root.rglob("*.py"):
        text = path.read_text()
        new = text.replace(
            "ergon_core.core.runtime.events",
            "ergon_core.core.application.events",
        )
        if new != text:
            path.write_text(new)
PY
```

Now delete the empty runtime root:

Run:

```bash
rmdir ergon_core/ergon_core/core/runtime
```

Expected: command succeeds because all runtime subpackages and files have moved.

- [ ] **Step 2: Add durable root guard**

Append to `tests/unit/architecture/test_core_schema_sources.py`:

```python
def test_core_uses_hybrid_domain_layout_roots() -> None:
    core = ROOT / "ergon_core/ergon_core/core"

    expected_dirs = {
        "application",
        "domain",
        "infrastructure",
        "persistence",
        "rest_api",
        "rl",
        "shared",
    }
    actual_dirs = {path.name for path in core.iterdir() if path.is_dir() and path.name != "__pycache__"}

    assert expected_dirs <= actual_dirs
    assert "runtime" not in actual_dirs
    assert "api" not in actual_dirs
    assert "definitions" not in actual_dirs
    assert "composition" not in actual_dirs
    assert "sandbox" not in actual_dirs
    assert "dashboard" not in actual_dirs
```

- [ ] **Step 3: Add import direction guard**

Append to `tests/unit/architecture/test_core_schema_sources.py`:

```python
def test_core_hybrid_layout_import_directions() -> None:
    forbidden_imports = {
        "domain": (
            "ergon_core.core.application",
            "ergon_core.core.persistence",
            "ergon_core.core.infrastructure",
            "ergon_core.core.rest_api",
        ),
        "persistence": (
            "ergon_core.core.application",
            "ergon_core.core.infrastructure",
            "ergon_core.core.rest_api",
        ),
        "application": (
            "ergon_core.core.rest_api",
            "ergon_core.core.infrastructure.inngest.handlers",
        ),
    }

    offenders: list[str] = []
    for root_name, snippets in forbidden_imports.items():
        root = ROOT / "ergon_core/ergon_core/core" / root_name
        for path in root.rglob("*.py"):
            text = path.read_text()
            for snippet in snippets:
                if snippet in text:
                    offenders.append(f"{path.relative_to(ROOT)} imports {snippet}")

    assert offenders == []
```

- [ ] **Step 4: Add job adapter split guard**

Append to `tests/unit/architecture/test_core_schema_sources.py`:

```python
def test_application_jobs_do_not_own_inngest_decorators() -> None:
    jobs_root = ROOT / "ergon_core/ergon_core/core/application/jobs"
    offenders: list[str] = []

    for path in jobs_root.rglob("*.py"):
        text = path.read_text()
        if "@inngest_client.create_function" in text or "import inngest" in text:
            offenders.append(str(path.relative_to(ROOT)))
        if "ergon_core.core.infrastructure.inngest.handlers" in text:
            offenders.append(str(path.relative_to(ROOT)))

    assert offenders == []
```

- [ ] **Step 5: Run architecture tests**

Run:

```bash
uv run pytest tests/unit/architecture -q
```

Expected: PASS except the temporary exact-layout test may still fail if additional unexpected files exist. If it fails, inspect the exact `unexpected` list and decide whether the target doc should include those files or the files should move/delete.

## Task 10: Finalize Exact Layout, Delete Temporary Test

**Files:**
- Delete: `tests/unit/architecture/test_core_hybrid_layout_temporary.py`
- Modify: `docs/superpowers/plans/2026-04-28-core-hybrid-domain-layout.md` if any final file names changed during implementation
- Test: architecture suite and focused regression suite

- [ ] **Step 1: Run temporary exact-layout test one last time**

Run:

```bash
uv run pytest tests/unit/architecture/test_core_hybrid_layout_temporary.py -q
```

Expected: PASS. This proves the temporary exact target was achieved before deleting the brittle guard.

- [ ] **Step 2: Delete the temporary test**

Run:

```bash
rm tests/unit/architecture/test_core_hybrid_layout_temporary.py
```

- [ ] **Step 3: Run architecture and focused regression tests**

Run:

```bash
uv run pytest tests/unit/architecture tests/unit/runtime/test_workflow_service.py tests/unit/runtime/test_task_execution_repository.py tests/unit/runtime/test_inngest_criterion_executor.py tests/unit/dashboard/test_communication_threads.py tests/unit/cli/test_experiment_cli.py tests/unit/benchmarks/test_swebench_sandbox_manager.py -q
```

Expected: PASS.

- [ ] **Step 4: Run ruff on moved source and tests**

Run:

```bash
uv run ruff check ergon_core ergon_cli ergon_builtins tests/unit/architecture
```

Expected: PASS.

## Task 11: Broad Verification

**Files:**
- Modify: none unless tests reveal missed imports
- Test: broad unit/integration suite as time permits

- [ ] **Step 1: Search for stale paths**

Run:

```bash
rg "ergon_core\\.core\\.(runtime|api|definitions|composition|sandbox|dashboard)|core/runtime|core/api|core/definitions|core/composition|core/sandbox|core/dashboard" ergon_core ergon_cli ergon_builtins tests docs/superpowers/plans/2026-04-28-core-hybrid-domain-layout.md
```

Expected: no stale code imports. Documentation may mention old paths only in current-to-target move maps.

- [ ] **Step 2: Run broad unit tests**

Run:

```bash
uv run pytest tests/unit -q
```

Expected: PASS, or failures only from known environment import-resolution issues. Fix any migration-related import failures.

- [ ] **Step 3: Run targeted integration tests**

Run:

```bash
uv run pytest tests/integration/propagation tests/integration/restart tests/integration/smokes -q
```

Expected: PASS, or failures clearly unrelated to package movement.

## Self-Review Checklist

- Every moved package has a target path in the plan.
- The temporary exact folder test is added first and deleted in the final cleanup.
- `core/rl` remains top-level.
- `core/rest_api` is distinct from public `ergon_core.api`.
- Inngest semantic jobs land in `application/jobs`; adapters land in `infrastructure/inngest/handlers`.
- No compatibility aliases are required by the plan.
- No git commits are required by the plan.
