# PR 7 — Persistence Collapse Behind Bridges

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:subagent-driven-development` or
> `superpowers:executing-plans` to implement this plan task-by-task.

**Goal:** Make new definitions and runs work without `ExperimentRecord`,
while old read paths remain bridged until final deletion.

**Architecture:** Add definition metadata columns and canonical launch by
`definition_id`. Keep `ExperimentRecord` importable for old read models until
PR 11.

**Tech Stack:** SQLModel, Alembic additive migration, read-model tests.

---

## Files

**Modify:**

```text
ergon_core/ergon_core/core/persistence/definitions/models.py
ergon_core/ergon_core/core/persistence/telemetry/models.py
ergon_core/ergon_core/core/application/experiments/definition_writer.py
ergon_core/ergon_core/core/application/experiments/launch.py
ergon_core/ergon_core/core/application/experiments/service.py
ergon_core/ergon_core/core/application/read_models/experiments.py
ergon_core/ergon_core/core/application/read_models/runs.py
ergon_core/ergon_core/core/application/read_models/cohorts.py
ergon_core/tests/unit/runtime/test_experiment_launch_service.py
ergon_core/tests/unit/runtime/test_experiment_read_service.py
ergon_core/tests/unit/state/test_type_invariants.py
```

**Create:**

```text
ergon_core/migrations/versions/<revision>_definition_metadata_and_launch.py
```

## Current State

`ExperimentRecord` carries user-facing metadata and run launch loads by
`experiment_id`. `ExperimentDefinition` carries only benchmark type,
metadata JSON, and created timestamp.

## Target State For This PR

New path:

```python
definition = ExperimentDefinition(
    id=definition_id,
    name=experiment.name or benchmark_type,
    description=experiment.description,
    metadata_json=dict(experiment.metadata),
    created_by="cli",
)
run = launch_run(definition_id)
```

Old `ExperimentRecord` remains for old read models.

## Task 1: Add Definition Metadata

**Files:**

- Modify: `ergon_core/ergon_core/core/persistence/definitions/models.py`
- Create: migration file

- [ ] **Step 1: Add fields**

```python
name: str = Field(index=True)
description: str | None = None
created_by: str | None = None
```

Keep `metadata_json` as the JSONB/free-form metadata field.

- [ ] **Step 2: Add migration**

```python
def upgrade() -> None:
    op.add_column("experiment_definitions", sa.Column("name", sa.Text(), nullable=True))
    op.add_column("experiment_definitions", sa.Column("description", sa.Text(), nullable=True))
    op.add_column("experiment_definitions", sa.Column("created_by", sa.Text(), nullable=True))
    op.create_index("ix_experiment_definitions_name", "experiment_definitions", ["name"])
    op.execute("UPDATE experiment_definitions SET name = benchmark_type WHERE name IS NULL")
    op.alter_column("experiment_definitions", "name", nullable=False)
```

Downgrade drops the index and columns.

## Task 2: Persist Metadata

**Files:**

- Modify: `ergon_core/ergon_core/core/application/experiments/definition_writer.py`

This task is the **denormalization site** for `02-persistence-layer.md`
§3's indexed-column rule. `name` and `description` round-trip through
`experiment_json` AND are written into dedicated indexed columns so the
dashboard can `SELECT id FROM experiment_definitions WHERE name = ...`
without JSON path queries. The extraction happens here, inline, at
write time — there is **no** `Experiment.metadata_columns()` helper or
`model_validator` that produces the column dict, because:

1. The writer is the only caller; abstracting it adds indirection
   without a second consumer.
2. The column set is short (three fields); a helper would barely save
   code.
3. Keeping the extraction inline keeps the SQL writer's full shape
   visible in one place, which matters for the v1-audit-style review
   that asks "what columns get populated when".

If a second caller appears later (e.g. an admin tool that wants to
reproduce the denormalization for back-fills), promote the inline block
to a `_metadata_columns(experiment)` private helper in the same module
at that point — not preemptively.

- [ ] **Step 1: Change definition row construction**

PR 5 already lands the public `Experiment` with first-class typed
fields for `name`, `description`, `created_by`, and `metadata`. By
PR 7, these are real attributes on every `Experiment` instance — no
`getattr` fallback is needed, and `created_by` is no longer buried in
the metadata dict.

Replace:

```python
definition_row = ExperimentDefinition(
    id=definition_id,
    benchmark_type=benchmark_type,
    metadata_json=dict(experiment.metadata),
    created_at=now,
)
```

with:

```python
definition_row = ExperimentDefinition(
    id=definition_id,
    benchmark_type=benchmark_type,
    name=experiment.name if experiment.name is not None else benchmark_type,
    description=experiment.description,
    created_by=experiment.created_by,
    metadata_json=dict(experiment.metadata),
    created_at=now,
)
```

The `if ... is not None` form (rather than `experiment.name or
benchmark_type`) is deliberate: `or` would also fall through on the
empty string, which is a valid (if unusual) author choice; `is not
None` only falls through when the author left the field unset.

If a CLI or test ever constructs an `ExperimentDefinition` *without*
going through `Experiment(...)` first, that's a typing gap to fix at
the caller — not a `getattr` bridge to add here. PR 11's
"`test_no_type_circumventors.py`" guard catches re-introductions.

## Task 3: Add Canonical Launch By Definition

**Files:**

- Modify: `ergon_core/ergon_core/core/application/experiments/launch.py`

- [ ] **Step 1: Add public function**

```python
async def launch_run(
    definition_id: UUID,
    *,
    metadata: Mapping[str, Any] | None = None,
    emit_workflow_started: WorkflowStartedEmitter | None = None,
) -> ExperimentRunResult:
    emitter = emit_workflow_started or _emit_workflow_started
    with get_session() as session:
        definition = session.get(ExperimentDefinition, definition_id)
        if definition is None:
            raise ValueError(f"ExperimentDefinition {definition_id} not found")
        run = create_run(
            DefinitionHandle(definition_id=definition.id, benchmark_type=definition.benchmark_type),
            experiment_id=None,
            workflow_definition_id=definition.id,
            instance_key=None,
            worker_team_json={},
            evaluator_slug=None,
            model_target=None,
            sandbox_slug=None,
            dependency_extras_json={},
            assignment_json=dict(metadata or {}),
            seed=None,
        )
    await emitter(run.id, definition_id)
    return ExperimentRunResult(
        experiment_id=definition_id,
        run_ids=[run.id],
        workflow_definition_ids=[definition_id],
    )
```

The `create_run` call still accepts old telemetry fields. PR 11 narrows it.

- [ ] **Step 2: Make `ExperimentService.run_experiment` delegate**

If the request field is still named `experiment_id`, detect whether it is an
`ExperimentDefinition` first. Fall back to `ExperimentRecord` only if no
definition exists.

## Task 4: Read Models Prefer Definitions

**Files:**

- Modify read model files listed above

- [ ] **Step 1: Change list/show queries**

Queries should select `ExperimentDefinition` first and map:

```python
experiment_id = definition.id
name = definition.name
description = definition.description
benchmark_type = definition.benchmark_type
metadata = definition.parsed_metadata()
```

Keep an `ExperimentRecord` fallback method named
`_legacy_experiment_record_detail` for old rows.

## Task 5: Tests

**Files:**

- Modify: `ergon_core/tests/unit/runtime/test_experiment_launch_service.py`
- Modify: `ergon_core/tests/unit/runtime/test_experiment_read_service.py`

- [ ] **Step 1: Launch test**

```python
@pytest.mark.asyncio
async def test_launch_run_accepts_definition_id_without_experiment_record(session):
    definition = ExperimentDefinition(
        benchmark_type="mini",
        name="mini",
        metadata_json={},
    )
    session.add(definition)
    session.commit()

    result = await launch_run(definition.id, emit_workflow_started=AsyncMock())

    assert result.workflow_definition_ids == [definition.id]
    assert result.run_ids
```

- [ ] **Step 2: Read model test**

```python
from sqlmodel import select

from ergon_core.core.application.read_models.experiments import (
    ExperimentReadService,
)
from ergon_core.core.persistence.definitions.models import ExperimentDefinition
from ergon_core.core.persistence.telemetry.models import ExperimentRecord


@pytest.mark.asyncio
async def test_read_service_returns_definition_metadata_without_experiment_record(
    session,
):
    definition = ExperimentDefinition(
        benchmark_type="mini",
        name="mini-experiment",
        description="smoke for read model",
        metadata_json={"created_by": "test"},
    )
    session.add(definition)
    session.commit()

    # Sanity-check setup: no ExperimentRecord exists for this id.
    assert (
        session.exec(
            select(ExperimentRecord).where(ExperimentRecord.id == definition.id)
        ).first()
        is None
    )

    detail = await ExperimentReadService().get_experiment(definition.id)

    assert detail is not None
    assert detail.experiment_id == definition.id
    assert detail.name == "mini-experiment"
    assert detail.description == "smoke for read model"
    assert detail.benchmark_type == "mini"
    assert detail.metadata.get("created_by") == "test"


@pytest.mark.asyncio
async def test_read_service_falls_back_to_experiment_record_for_legacy_rows(
    session,
):
    """Old rows with an ExperimentRecord but no ExperimentDefinition name
    still resolve via the legacy path until PR 11 deletes ExperimentRecord."""

    legacy = ExperimentRecord(name="legacy-only", benchmark_slug="mini")
    session.add(legacy)
    session.commit()

    detail = await ExperimentReadService().get_experiment(legacy.id)
    assert detail is not None
    assert detail.name == "legacy-only"
```

- [ ] **Step 3: Run focused tests**

```bash
uv run pytest ergon_core/tests/unit/runtime/test_experiment_launch_service.py \
  ergon_core/tests/unit/runtime/test_experiment_read_service.py \
  ergon_core/tests/unit/state/test_type_invariants.py -q
```

## Task 6: Flip XFails Landed By This PR

**Files:**

- Modify: `ergon_core/tests/unit/runtime/test_walkthrough_smoketest.py`
- Create: `ergon_core/ergon_core/core/application/experiments/errors.py`
- Modify: `ergon_core/ergon_core/core/application/experiments/repository.py`
- Modify: `ergon_core/tests/unit/architecture/test_repository_companion_files.py`

PR 7 lands `persist_definition` writing only the collapsed definition
table; the corresponding smoketest case flips green. PR 7 is also the
natural home for adding `experiments/errors.py` since this PR is
already heavily editing the experiments package.

- [ ] **Step 1: Remove the xfail on `test_persist_definition_writes_only_intended_tables`**

In `test_walkthrough_smoketest.py`, delete the
`@pytest.mark.xfail(reason="PR 7: ...")` decorator. The test body
already asserts the correct invariant (one `ExperimentDefinition` row,
N `ExperimentDefinitionTask` rows) and now passes against the collapsed
schema this PR delivers.

- [ ] **Step 2: Add `experiments/errors.py`**

```python
"""Errors raised by the experiments domain.

Typed exceptions so callers can `except DefinitionNotFoundError:`
specifically rather than catching generic `ValueError` and string-
matching the message. See 07-test-strategy.md § Repository layer
standard rule 8.
"""

from uuid import UUID


class ExperimentDomainError(Exception):
    """Base for all experiments-domain errors."""


class DefinitionNotFoundError(ExperimentDomainError):
    """Lookup failed for an `ExperimentDefinition` row."""

    def __init__(self, definition_id: UUID) -> None:
        super().__init__(f"ExperimentDefinition {definition_id} not found")
        self.definition_id = definition_id


class DefinitionTaskNotFoundError(ExperimentDomainError):
    """Lookup failed for an `ExperimentDefinitionTask` row."""

    def __init__(self, task_id: UUID) -> None:
        super().__init__(f"ExperimentDefinitionTask {task_id} not found")
        self.task_id = task_id


class DefinitionInstanceNotFoundError(ExperimentDomainError):
    """Lookup failed for an `ExperimentDefinitionInstance` row."""

    def __init__(self, instance_id: UUID) -> None:
        super().__init__(
            f"ExperimentDefinitionInstance {instance_id} not found"
        )
        self.instance_id = instance_id
```

- [ ] **Step 3: Replace `ValueError` raises in the repository**

In `experiments/repository.py`, replace:

```python
raise ValueError(f"ExperimentDefinitionTask {task_id} not found")
raise ValueError(f"ExperimentDefinitionInstance {task.instance_id} not found")
```

with:

```python
raise DefinitionTaskNotFoundError(task_id)
raise DefinitionInstanceNotFoundError(task.instance_id)
```

Update imports accordingly. Run `rg "ExperimentDefinitionTask.*not found"`
to confirm no other inline raise sites remain.

- [ ] **Step 4: Remove the xfail entry**

In `test_repository_companion_files.py`, delete:

```python
("test_package_has_errors_py_if_it_raises",
 "ergon_core/ergon_core/core/application/experiments"):
    "PR 7: add experiments/errors.py with typed DefinitionNotFoundError "
    "and replace ValueError raises",
```

- [ ] **Step 5: Run the ledgers**

```bash
uv run pytest \
  ergon_core/tests/unit/runtime/test_walkthrough_smoketest.py \
  ergon_core/tests/unit/architecture/test_repository_companion_files.py -q
```

Expected: the PR 7 cases PASS; remaining cases still XFAIL.

## PR Ledger

Invariant landed: new definitions can launch without experiment records.

Bridge code introduced: `ExperimentRecord` fallback read/launch path.

Old path still intentionally alive: `ExperimentRecord`, old run telemetry
fields.

Deletion gate: PR 11 deletes `ExperimentRecord` and narrows `create_run`.

Tests added or updated: launch-by-definition and read-model tests.

Modules owned by this PR: definition metadata, launch, read models.
