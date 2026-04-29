# Persistent Component Catalog And Test Layout Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make component registration understandable across processes by splitting tests by package ownership, persisting component slug-to-import references in Postgres, and deleting test/fixture env-var switches.

**Architecture:** First reorganize tests so package boundaries are visible and cross-process E2E stays black-box. Then add a trusted `component_catalog` table in `ergon_core` that stores component kind, slug, module, qualname, and metadata. Finally, update the Pydantic registry to publish/load catalog rows, make runtime jobs resolve components through the catalog-backed registry, and remove `ENABLE_TEST_HARNESS`, `TEST_HARNESS_SECRET`, `ERGON_STARTUP_PLUGINS`, `ENABLE_SMOKE_FIXTURES`, and `ERGON_SKIP_INFRA_CHECK`.

**Tech Stack:** Python 3.13, SQLModel, Alembic, Pydantic v2, pytest, FastAPI, argparse CLI, existing uv/pnpm scripts.

---

## Service Design Constraint

Use one catalog boundary: `ComponentCatalogService`. Do not implement both a service and repository for the catalog. The service owns the contract for publishing refs, requiring refs, and loading import refs; keep the API small so it does not become a second registry.

## Mental Model

The final system should be explainable as:

1. Packages define components in Python code.
2. Packages publish component references into Postgres as trusted catalog rows.
3. Experiment definitions store stable slugs.
4. API/Inngest/CLI resolve slugs through the shared catalog, import the Python reference, and instantiate the component.
5. Tests are package-owned; only black-box E2E crosses process boundaries.

The Pydantic registry remains useful as an authoring and publishing helper, but runtime resolution should read from Postgres every time. These lookups are not hot enough to justify an in-memory process-local cache, and always reading the catalog keeps cross-process behavior easier to reason about.

## ID Model

Use one worker-facing task identity:

```python
Task.task_id == RunGraphNode.id
```

`RunGraphNode.id` is the runtime task id. It exists for every executable task in a run, including dynamically spawned subtasks. This is the only task id worker authors should see.

Use explicit names for internal/template identity:

```python
definition_id       # ExperimentDefinition.id, the static experiment template
node_id             # RunGraphNode.id, the runtime task identity
execution_id        # RunTaskExecution.id, one attempt to execute a node
```

Do not pass `definition_task_id` through public `Task` or runtime event/job payloads. Keep it only as an optional persisted relationship on rows such as `RunGraphNode` / `RunTaskExecution` when the application layer needs static-template joins. If runtime needs definition data, resolve it from `node_id` through the persisted graph/run links (`RunGraphNode.run_id` -> `RunRecord.workflow_definition_id` -> `ExperimentDefinition`) or use the already available run/definition context in the application layer.

## File Structure

- Create package-owned test roots:
  - `ergon_core/tests/`
  - `ergon_builtins/tests/`
  - `ergon_cli/tests/`
  - optionally `ergon_infra/tests/`
- Keep cross-package black-box tests at:
  - `tests/e2e/`
  - `tests/real_llm/`
  - `tests/fixtures/` only for fixtures intentionally shared by black-box tests.
- Create component catalog files:
  - `ergon_core/ergon_core/core/persistence/components/models.py`
  - `ergon_core/ergon_core/core/application/components/catalog.py`
  - `ergon_core/migrations/versions/<new>_add_component_catalog.py`
- Modify registry/bootstrap files:
  - `ergon_core/ergon_core/api/benchmark/task.py`
  - `ergon_core/ergon_core/api/worker/context.py`
  - `ergon_core/ergon_core/api/worker/worker.py`
  - `ergon_core/ergon_core/api/worker/__init__.py`
  - `ergon_core/ergon_core/api/registry.py`
  - `ergon_builtins/ergon_builtins/registry.py`
  - `ergon_builtins/ergon_builtins/registry_core.py`
  - `ergon_builtins/ergon_builtins/registry_data.py`
  - `tests/fixtures/smoke_components/__init__.py`
- Modify runtime resolution files:
  - `ergon_core/ergon_core/core/application/events/task_events.py`
  - `ergon_core/ergon_core/core/application/jobs/models.py`
  - `ergon_core/ergon_core/core/application/jobs/worker_execute.py`
  - `ergon_core/ergon_core/core/application/jobs/execute_task.py`
  - `ergon_core/ergon_core/core/application/workflows/orchestration.py`
  - `ergon_core/ergon_core/core/application/jobs/evaluate_task_run.py`
  - `ergon_core/ergon_core/core/application/jobs/sandbox_setup.py`
  - `ergon_core/ergon_core/core/application/jobs/persist_outputs.py`
  - `ergon_core/ergon_core/core/application/experiments/service.py`
  - `ergon_core/ergon_core/core/application/experiments/launch.py`
  - `ergon_core/ergon_core/core/application/workflows/service.py`
  - `ergon_core/ergon_core/core/application/tasks/management.py`
  - `ergon_core/ergon_core/core/domain/experiments/worker_spec.py`
- Modify harness/env-var files:
  - `ergon_core/ergon_core/core/shared/settings.py`
  - `ergon_core/ergon_core/core/rest_api/app.py`
  - `ergon_core/ergon_core/core/rest_api/test_harness.py`
  - `docker-compose.yml`
  - `.github/workflows/e2e-benchmarks.yml`
  - `.github/workflows/ci-fast.yml`
  - `package.json`
  - `scripts/smoke_local_up.sh`
  - `scripts/smoke_local_run.sh`
  - `tests/e2e/conftest.py`
  - `tests/integration/conftest.py`
  - dashboard test harness clients/routes that reference `TEST_HARNESS_SECRET`.

---

### Task 1: Create Package-Owned Test Layout Guardrails

**Files:**
- Create: `tests/unit/architecture/test_package_test_layout.py`
- Modify later: `package.json`

- [ ] **Step 1: Write architecture test for target test layout**

Create `tests/unit/architecture/test_package_test_layout.py`:

```python
from pathlib import Path


def test_package_owned_test_roots_exist() -> None:
    assert Path("ergon_core/tests").is_dir()
    assert Path("ergon_builtins/tests").is_dir()
    assert Path("ergon_cli/tests").is_dir()


def test_root_tests_are_black_box_or_shared_only() -> None:
    allowed = {
        "__init__.py",
        "__pycache__",
        "conftest.py",
        "e2e",
        "fixtures",
        "integration",
        "real_llm",
    }
    root_entries = {path.name for path in Path("tests").iterdir()}
    assert root_entries <= allowed
```

- [ ] **Step 2: Run the architecture test and verify it fails**

Run:

```bash
uv run pytest tests/unit/architecture/test_package_test_layout.py -q
```

Expected: FAIL because package-owned test roots do not exist and `tests/unit` still contains package-owned tests.

- [ ] **Step 3: Create package-owned test directories**

Create:

```text
ergon_core/tests/unit/
ergon_core/tests/integration/
ergon_builtins/tests/unit/
ergon_builtins/tests/integration/
ergon_cli/tests/unit/
ergon_cli/tests/integration/
```

Add empty `__init__.py` files only if import/package semantics require them. Prefer no `__init__.py` for pytest discovery unless an existing pattern depends on package imports.

- [ ] **Step 4: Update `package.json` scripts to include both old and new roots**

Modify backend test scripts temporarily so moved tests can be discovered while migration is incremental:

```json
"test:be:unit": "uv run pytest ergon_core/tests/unit ergon_builtins/tests/unit ergon_cli/tests/unit tests/unit -q -n auto --durations=20",
"test:be:coverage": "uv run pytest ergon_core/tests/unit ergon_builtins/tests/unit ergon_cli/tests/unit tests/unit tests/integration --cov=ergon_core --cov=ergon_builtins --cov-report=term-missing --cov-report=xml:coverage.xml"
```

- [ ] **Step 5: Run package layout test**

Run:

```bash
uv run pytest tests/unit/architecture/test_package_test_layout.py -q
```

Expected: still FAIL until tests are moved in Tasks 2-4.

---

### Task 2: Move Core-Owned Unit Tests To `ergon_core/tests`

**Files:**
- Move tests from `tests/unit/api`, `tests/unit/runtime`, `tests/unit/sandbox`, selected `tests/unit/architecture`, selected `tests/unit/state`, and core app tests into `ergon_core/tests/unit`.
- Modify imports only where they reference moved fixture paths.

- [ ] **Step 1: Move clearly core-owned directories**

Move:

```text
tests/unit/api/ -> ergon_core/tests/unit/api/
tests/unit/runtime/ -> ergon_core/tests/unit/runtime/
tests/unit/sandbox/ -> ergon_core/tests/unit/sandbox/
tests/unit/persistence/ -> ergon_core/tests/unit/persistence/
tests/unit/dashboard/ -> ergon_core/tests/unit/dashboard/
```

Move standalone core app tests:

```text
tests/unit/test_app_mounts_harness_conditionally.py -> ergon_core/tests/unit/test_app_mounts_harness_conditionally.py
tests/unit/test_dashboard_emitter_wiring.py -> ergon_core/tests/unit/test_dashboard_emitter_wiring.py
tests/unit/test_rollouts_di.py -> ergon_core/tests/unit/test_rollouts_di.py
tests/unit/test_test_harness.py -> ergon_core/tests/unit/test_test_harness.py
tests/unit/test_swebench_criterion_no_sandbox.py -> ergon_core/tests/unit/test_swebench_criterion_no_sandbox.py
```

- [ ] **Step 2: Move registry/core architecture tests**

Move:

```text
tests/unit/registry/ -> ergon_core/tests/unit/registry/
tests/unit/architecture/test_api_runs_boundary.py -> ergon_core/tests/unit/architecture/test_api_runs_boundary.py
tests/unit/architecture/test_core_schema_sources.py -> ergon_core/tests/unit/architecture/test_core_schema_sources.py
tests/unit/architecture/test_model_field_descriptions.py -> ergon_core/tests/unit/architecture/test_model_field_descriptions.py
tests/unit/architecture/test_no_test_logic_in_core.py -> ergon_core/tests/unit/architecture/test_no_test_logic_in_core.py
tests/unit/architecture/test_persistence_boundaries.py -> ergon_core/tests/unit/architecture/test_persistence_boundaries.py
tests/unit/architecture/test_public_api_boundaries.py -> ergon_core/tests/unit/architecture/test_public_api_boundaries.py
tests/unit/architecture/test_public_api_target_structure.py -> ergon_core/tests/unit/architecture/test_public_api_target_structure.py
tests/unit/architecture/test_smoke_fixture_package_boundary.py -> ergon_core/tests/unit/architecture/test_smoke_fixture_package_boundary.py
```

Leave `tests/unit/architecture/test_package_test_layout.py` at root until the migration is complete because it governs the whole repo.

- [ ] **Step 3: Run moved core tests**

Run:

```bash
uv run pytest ergon_core/tests/unit -q
```

Expected: PASS or failures that reveal imports still pointing at old `tests/unit/...` paths.

- [ ] **Step 4: Fix import paths revealed by failures**

For each failure, update imports to either:

```python
from tests.fixtures...
```

for intentionally shared black-box fixtures, or local package test helpers under:

```python
from ergon_core.tests...
```

Do not import `ergon_builtins` in core unit tests unless the test is explicitly an integration/boundary test that names that dependency.

- [ ] **Step 5: Run old and new unit suites**

Run:

```bash
uv run pytest ergon_core/tests/unit tests/unit -q
```

Expected: PASS, with fewer tests left under `tests/unit`.

---

### Task 3: Move Builtins-Owned Tests To `ergon_builtins/tests`

**Files:**
- Move benchmark, worker, builtins state, smoke component tests that assert builtins behavior.

- [ ] **Step 1: Move builtins benchmark/worker tests**

Move:

```text
tests/unit/benchmarks/ -> ergon_builtins/tests/unit/benchmarks/
tests/unit/builtins/ -> ergon_builtins/tests/unit/builtins/
tests/unit/workers/ -> ergon_builtins/tests/unit/workers/
tests/unit/state/test_benchmark_contract.py -> ergon_builtins/tests/unit/state/test_benchmark_contract.py
tests/unit/state/test_gdpeval_benchmark.py -> ergon_builtins/tests/unit/state/test_gdpeval_benchmark.py
tests/unit/state/test_research_rubrics_benchmark.py -> ergon_builtins/tests/unit/state/test_research_rubrics_benchmark.py
tests/unit/state/test_research_rubrics_workers.py -> ergon_builtins/tests/unit/state/test_research_rubrics_workers.py
tests/unit/state/test_llm_judge_runtime_injection.py -> ergon_builtins/tests/unit/state/test_llm_judge_runtime_injection.py
tests/unit/state/test_criteria_do_not_spawn_sandboxes.py -> ergon_builtins/tests/unit/state/test_criteria_do_not_spawn_sandboxes.py
```

- [ ] **Step 2: Move smoke component unit tests**

Move:

```text
tests/unit/smoke_base/ -> ergon_builtins/tests/unit/smoke_base/
```

Rationale: the fixture source remains at `tests/fixtures/smoke_components` because E2E consumes it as shared black-box fixture code, but unit tests for that fixture behavior should not live in root `tests/unit`.

- [ ] **Step 3: Run builtins tests**

Run:

```bash
uv run pytest ergon_builtins/tests/unit -q
```

Expected: PASS or import failures from moved helper paths.

- [ ] **Step 4: Fix moved builtins imports**

Update any relative references from old root locations. Keep production imports from `ergon_builtins.*` unchanged.

- [ ] **Step 5: Run package test subset**

Run:

```bash
uv run pytest ergon_builtins/tests/unit ergon_core/tests/unit tests/unit -q
```

Expected: PASS.

---

### Task 4: Move CLI-Owned Tests To `ergon_cli/tests`

**Files:**
- Move CLI unit tests and CLI-specific state tests.

- [ ] **Step 1: Move CLI tests**

Move:

```text
tests/unit/cli/ -> ergon_cli/tests/unit/cli/
tests/unit/state/test_onboard_profile.py -> ergon_cli/tests/unit/state/test_onboard_profile.py
tests/unit/state/test_env_writer.py -> ergon_cli/tests/unit/state/test_env_writer.py
tests/unit/state/test_openrouter_model_resolution.py -> ergon_cli/tests/unit/state/test_openrouter_model_resolution.py
tests/unit/state/test_subtask_lifecycle_toolkit.py -> ergon_cli/tests/unit/state/test_subtask_lifecycle_toolkit.py
tests/unit/state/test_workflow_cli_tool.py -> ergon_cli/tests/unit/state/test_workflow_cli_tool.py
```

- [ ] **Step 2: Run CLI tests**

Run:

```bash
uv run pytest ergon_cli/tests/unit -q
```

Expected: PASS or import failures that identify old paths.

- [ ] **Step 3: Update `package.json` to remove old unit root once empty**

After Tasks 2-4, if `tests/unit` contains only architecture migration tests or is empty, update scripts:

```json
"test:be:unit": "uv run pytest ergon_core/tests/unit ergon_builtins/tests/unit ergon_cli/tests/unit -q -n auto --durations=20"
```

If a small root `tests/unit` remains for repo-wide architecture tests, include it explicitly:

```json
"test:be:unit": "uv run pytest ergon_core/tests/unit ergon_builtins/tests/unit ergon_cli/tests/unit tests/unit -q -n auto --durations=20"
```

- [ ] **Step 4: Run package layout guardrail**

Run:

```bash
uv run pytest tests/unit/architecture/test_package_test_layout.py -q
```

Expected: PASS.

---

### Task 5: Add Component Catalog Persistence Model And Migration

**Files:**
- Create: `ergon_core/ergon_core/core/persistence/components/models.py`
- Modify: `ergon_core/migrations/env.py`
- Create: `ergon_core/migrations/versions/<revision>_add_component_catalog.py`
- Test: `ergon_core/tests/unit/registry/test_component_catalog_model.py`

- [ ] **Step 1: Write catalog model tests**

Create `ergon_core/tests/unit/registry/test_component_catalog_model.py`:

```python
import pytest

from ergon_core.core.persistence.components.models import ComponentCatalogEntry


def test_component_catalog_entry_round_trips_metadata() -> None:
    entry = ComponentCatalogEntry(
        kind="worker",
        slug="training-stub",
        module="ergon_builtins.shared.workers.training_stub_worker",
        qualname="TrainingStubWorker",
        package="ergon-builtins",
        metadata_json={"description": "offline worker"},
    )

    assert entry.parsed_metadata() == {"description": "offline worker"}


def test_component_catalog_entry_rejects_invalid_kind() -> None:
    with pytest.raises(ValueError, match="kind must be one of"):
        ComponentCatalogEntry(
            kind="not-a-kind",
            slug="bad",
            module="pkg.mod",
            qualname="Thing",
        )
```

- [ ] **Step 2: Run catalog model tests and verify they fail**

Run:

```bash
uv run pytest ergon_core/tests/unit/registry/test_component_catalog_model.py -q
```

Expected: FAIL because the model module does not exist.

- [ ] **Step 3: Implement SQLModel catalog entry**

Create `ergon_core/ergon_core/core/persistence/components/models.py`:

```python
"""Persistent component catalog shared across CLI/API/Inngest processes."""

from datetime import datetime
from uuid import UUID, uuid4

from ergon_core.core.shared.json_types import JsonObject
from ergon_core.core.shared.utils import utcnow as _utcnow
from pydantic import model_validator
from sqlalchemy import JSON, Column, DateTime, UniqueConstraint
from sqlmodel import Field, SQLModel

TZDateTime = DateTime(timezone=True)
COMPONENT_KINDS = {"worker", "benchmark", "evaluator", "sandbox_manager"}


class ComponentCatalogEntry(SQLModel, table=True):
    __tablename__ = "component_catalog"
    __table_args__ = (UniqueConstraint("kind", "slug", name="uq_component_catalog_kind_slug"),)

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    kind: str = Field(index=True)
    slug: str = Field(index=True)
    module: str
    qualname: str
    package: str | None = Field(default=None, index=True)
    version: str | None = None
    metadata_json: dict = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=_utcnow, sa_type=TZDateTime)
    updated_at: datetime = Field(default_factory=_utcnow, sa_type=TZDateTime)

    def parsed_metadata(self) -> JsonObject:
        return self.__class__._parse_metadata(self.metadata_json)

    @classmethod
    def _parse_metadata(cls, data: dict) -> JsonObject:
        if not isinstance(data, dict):
            raise ValueError(f"metadata_json must be a dict, got {type(data).__name__}")
        return data

    @model_validator(mode="after")
    def _validate_entry(self) -> "ComponentCatalogEntry":
        if self.kind not in COMPONENT_KINDS:
            allowed = ", ".join(sorted(COMPONENT_KINDS))
            raise ValueError(f"kind must be one of: {allowed}")
        if not self.slug:
            raise ValueError("slug must be non-empty")
        if not self.module:
            raise ValueError("module must be non-empty")
        if not self.qualname:
            raise ValueError("qualname must be non-empty")
        self.__class__._parse_metadata(self.metadata_json)
        return self
```

- [ ] **Step 4: Import component models in Alembic env**

Modify `ergon_core/migrations/env.py`:

```python
import ergon_core.core.persistence.components.models
```

Add it beside the other persistence model imports.

- [ ] **Step 5: Add Alembic migration**

Create a migration file under `ergon_core/migrations/versions/` with a new revision id:

```python
"""add component catalog

Revision ID: d1e2f3a4b5c6
Revises: c2d3e4f5a6b7
Create Date: 2026-04-29
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d1e2f3a4b5c6"
down_revision: str | None = "c2d3e4f5a6b7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "component_catalog",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("slug", sa.String(), nullable=False),
        sa.Column("module", sa.String(), nullable=False),
        sa.Column("qualname", sa.String(), nullable=False),
        sa.Column("package", sa.String(), nullable=True),
        sa.Column("version", sa.String(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("kind", "slug", name="uq_component_catalog_kind_slug"),
    )
    op.create_index("ix_component_catalog_kind", "component_catalog", ["kind"], unique=False)
    op.create_index("ix_component_catalog_slug", "component_catalog", ["slug"], unique=False)
    op.create_index("ix_component_catalog_package", "component_catalog", ["package"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_component_catalog_package", table_name="component_catalog")
    op.drop_index("ix_component_catalog_slug", table_name="component_catalog")
    op.drop_index("ix_component_catalog_kind", table_name="component_catalog")
    op.drop_table("component_catalog")
```

Before choosing `down_revision`, inspect the current migration head with:

```bash
uv run alembic -c ergon_core/alembic.ini heads
```

Use the actual head instead of the placeholder if different.

- [ ] **Step 6: Run catalog model tests**

Run:

```bash
uv run pytest ergon_core/tests/unit/registry/test_component_catalog_model.py -q
```

Expected: PASS.

---

### Task 6: Add Component Catalog Service And Import Reference Loader

**Files:**
- Create: `ergon_core/ergon_core/core/application/components/__init__.py`
- Create: `ergon_core/ergon_core/core/application/components/catalog.py`
- Test: `ergon_core/tests/unit/registry/test_component_catalog_service.py`

- [ ] **Step 1: Write catalog service tests**

Create `ergon_core/tests/unit/registry/test_component_catalog_service.py`:

```python
import pytest
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from ergon_core.core.application.components.catalog import (
    ComponentCatalogService,
    ComponentRef,
    import_component_ref,
)
from ergon_core.core.persistence.components.models import ComponentCatalogEntry


def _session() -> Session:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    return Session(engine)


def test_upsert_and_require_component_ref() -> None:
    session = _session()
    service = ComponentCatalogService()

    service.upsert(
        session,
        ComponentRef(
            kind="worker",
            slug="training-stub",
            module="ergon_builtins.shared.workers.training_stub_worker",
            qualname="TrainingStubWorker",
            package="ergon-builtins",
            metadata={"install_hint": "none"},
        ),
    )
    session.commit()

    ref = service.require(session, kind="worker", slug="training-stub")
    assert ref.module == "ergon_builtins.shared.workers.training_stub_worker"
    assert ref.qualname == "TrainingStubWorker"
    assert ref.metadata == {"install_hint": "none"}


def test_upsert_updates_existing_ref() -> None:
    session = _session()
    service = ComponentCatalogService()

    service.upsert(session, ComponentRef(kind="worker", slug="x", module="old", qualname="Thing"))
    service.upsert(session, ComponentRef(kind="worker", slug="x", module="new", qualname="Other"))
    session.commit()

    rows = session.query(ComponentCatalogEntry).all()
    assert len(rows) == 1
    assert service.require(session, kind="worker", slug="x").module == "new"


def test_import_component_ref_imports_module_qualname() -> None:
    ref = ComponentRef(
        kind="worker",
        slug="component-ref",
        module="ergon_core.core.application.components.catalog",
        qualname="ComponentRef",
    )

    assert import_component_ref(ref) is ComponentRef


def test_require_unknown_component_lists_kind_and_slug() -> None:
    session = _session()

    with pytest.raises(ValueError, match="Unknown worker component slug 'missing'"):
        ComponentCatalogService().require(session, kind="worker", slug="missing")
```

- [ ] **Step 2: Run catalog service tests and verify they fail**

Run:

```bash
uv run pytest ergon_core/tests/unit/registry/test_component_catalog_service.py -q
```

Expected: FAIL because `ComponentCatalogService` does not exist.

- [ ] **Step 3: Implement component catalog service**

Create the package marker:

```python
"""Component catalog application services."""
```

Create `ergon_core/ergon_core/core/application/components/catalog.py`:

```python
"""Application service for trusted component catalog references."""

from importlib import import_module
from typing import Any

from ergon_core.core.persistence.components.models import ComponentCatalogEntry
from ergon_core.core.shared.json_types import JsonObject
from ergon_core.core.shared.utils import utcnow
from pydantic import BaseModel, ConfigDict, Field
from sqlmodel import Session, select


class ComponentRef(BaseModel):
    model_config = ConfigDict(frozen=True)

    kind: str
    slug: str
    module: str
    qualname: str
    package: str | None = None
    version: str | None = None
    metadata: JsonObject = Field(default_factory=dict)


class ComponentCatalogService:
    def upsert(self, session: Session, ref: ComponentRef) -> ComponentCatalogEntry:
        existing = session.exec(
            select(ComponentCatalogEntry).where(
                ComponentCatalogEntry.kind == ref.kind,
                ComponentCatalogEntry.slug == ref.slug,
            )
        ).one_or_none()

        row = existing or ComponentCatalogEntry(
            kind=ref.kind,
            slug=ref.slug,
            module=ref.module,
            qualname=ref.qualname,
        )
        row.module = ref.module
        row.qualname = ref.qualname
        row.package = ref.package
        row.version = ref.version
        row.metadata_json = dict(ref.metadata)
        row.updated_at = utcnow()
        session.add(row)
        return row

    def require(self, session: Session, *, kind: str, slug: str) -> ComponentRef:
        row = session.exec(
            select(ComponentCatalogEntry).where(
                ComponentCatalogEntry.kind == kind,
                ComponentCatalogEntry.slug == slug,
            )
        ).one_or_none()
        if row is None:
            raise ValueError(f"Unknown {kind} component slug {slug!r}")
        return _row_to_ref(row)

    def load_ref(self, ref: ComponentRef) -> Any:  # slopcop: ignore[no-typing-any]
        return import_component_ref(ref)


def import_component_ref(ref: ComponentRef) -> Any:  # slopcop: ignore[no-typing-any]
    target: Any = import_module(ref.module)  # slopcop: ignore[no-typing-any]
    for part in ref.qualname.split("."):
        target = getattr(target, part)
    return target


def _row_to_ref(row: ComponentCatalogEntry) -> ComponentRef:
    return ComponentRef(
        kind=row.kind,
        slug=row.slug,
        module=row.module,
        qualname=row.qualname,
        package=row.package,
        version=row.version,
        metadata=row.parsed_metadata(),
    )
```

- [ ] **Step 4: Run catalog service tests**

Run:

```bash
uv run pytest ergon_core/tests/unit/registry/test_component_catalog_service.py -q
```

Expected: PASS.

---

### Task 7: Move Execution Identity Out Of Worker Construction

**Files:**
- Modify: `ergon_core/ergon_core/api/benchmark/task.py`
- Modify: `ergon_core/ergon_core/api/worker/context.py`
- Modify: `ergon_core/ergon_core/api/worker/worker.py`
- Modify: `ergon_core/ergon_core/core/application/events/task_events.py`
- Modify: `ergon_core/ergon_core/core/application/jobs/models.py`
- Modify: `ergon_core/ergon_core/core/application/workflows/orchestration.py`
- Modify: `ergon_core/ergon_core/core/application/jobs/execute_task.py`
- Modify worker subclasses/factories that still require `task_id` or `sandbox_id`
- Test: `ergon_core/tests/unit/api/test_worker_contract.py`

- [ ] **Step 1: Write worker construction contract tests**

Create `ergon_core/tests/unit/api/test_worker_contract.py`:

```python
from collections.abc import AsyncGenerator
from uuid import uuid4

from ergon_core.api.benchmark import Task
from ergon_core.api.worker import Worker, WorkerContext, WorkerOutput
from ergon_core.api.worker.worker import WorkerStreamItem


class ContractSmokeWorker(Worker):
    type_slug = "contract-smoke-worker"

    async def execute(
        self,
        task: Task,
        *,
        context: WorkerContext,
    ) -> AsyncGenerator[WorkerStreamItem, None]:
        yield WorkerOutput(output="ok", success=True)


def test_worker_constructor_has_only_authoring_configuration() -> None:
    worker = ContractSmokeWorker(name="primary", model="stub:constant")

    assert isinstance(worker, ContractSmokeWorker)
    assert worker.name == "primary"
    assert worker.model == "stub:constant"


def test_task_carries_non_null_runtime_task_identity() -> None:
    node_id = uuid4()

    task = Task(
        task_id=node_id,
        task_slug="root",
        instance_key="default",
        description="Run root task",
    )

    assert task.task_id == node_id
```

- [ ] **Step 2: Run worker contract tests and verify they fail**

Run:

```bash
uv run pytest ergon_core/tests/unit/api/test_worker_contract.py -q
```

Expected: FAIL because `Task.task_id` does not exist yet and `Worker.__init__` still requires `task_id` and `sandbox_id`.

- [ ] **Step 3: Add non-null task identity to `Task`**

Modify `ergon_core/ergon_core/api/benchmark/task.py`:

```python
from uuid import UUID

class Task(BaseModel, Generic[PayloadT]):
    task_id: UUID
    task_slug: str
    instance_key: str
    description: str
```

`Task.task_id` is the worker-facing runtime task identity. It must always be `RunGraphNode.id`, not `ExperimentDefinitionTask.id`. Static definition tasks and dynamic subtasks both have a `RunGraphNode`, so worker authors get one non-null task id for every execution.

Remove the old nullable event/request `task_id` from runtime payloads. Runtime events/jobs should carry `node_id` as the task identity:

```python
node_id: UUID  # RunGraphNode.id; runtime task identity
```

Then remove the nullable worker-facing `task_id` from `WorkerContext`. The worker-facing contract should be:

```python
task.task_id        # non-null RunGraphNode.id
context.sandbox_id  # non-null sandbox identity
```

If helper tools need a sandbox/task key, pass `task.task_id` to those helpers explicitly when building them. Do not use `WorkerContext.task_id` as a second, nullable source of truth.

- [ ] **Step 3b: Remove nullable task identity from runtime payloads**

Remove internal event and job fields that currently use nullable `task_id` for `ExperimentDefinitionTask.id`:

```python
class TaskReadyEvent(InngestEventContract):
    run_id: UUID
    definition_id: UUID
    node_id: UUID
```

Apply the same shape to:

- `TaskStartedEvent`
- `TaskCompletedEvent`
- `TaskFailedEvent`
- `PrepareTaskExecutionCommand`
- `WorkerExecuteRequest`
- `EvaluateTaskRunRequest`

Keep `PreparedTaskExecution.node_id` as the canonical runtime task identity. Keep `RunGraphNode.definition_task_id` and `RunTaskExecution.definition_task_id` only as persisted relationships for static-template joins. If a service needs the static definition task row, it should load `RunGraphNode` by `node_id` and follow `RunGraphNode.definition_task_id`; do not carry that id through event payloads or public `Task`.

- [ ] **Step 4: Simplify `Worker.__init__`**

Modify `ergon_core/ergon_core/api/worker/worker.py`:

```python
def __init__(
    self,
    *,
    name: str,
    model: str | None,
    metadata: Mapping[str, Any] | None = None,  # slopcop: ignore[no-typing-any]
) -> None:
    self.name = name
    self.model = model
    self.metadata: dict[str, Any] = dict(metadata or {})  # slopcop: ignore[no-typing-any]
```

Do not keep `self.task_id` or `self.sandbox_id` on `Worker`. Workers should use `task.task_id` and `context.sandbox_id` inside `execute(...)`.

- [ ] **Step 5: Refactor builtin worker factories into Worker subclasses**

Replace factory functions such as `minif2f_react(...)` and `swebench_react(...)` with importable `Worker` subclasses. Those classes should build sandbox-bound tools inside `execute(...)`, using the runtime objects they already receive:

```python
async def execute(self, task: Task, *, context: WorkerContext) -> AsyncGenerator[WorkerStreamItem, None]:
    sandbox = MiniF2FSandboxManager().reconnect(context.sandbox_id)
    toolkit = MiniF2FToolkit(...)
    delegate = ReActWorker(
        name=self.name,
        model=self.model,
        tools=list(toolkit.get_tools()),
        system_prompt=MINIF2F_SYSTEM_PROMPT,
        max_iterations=30,
    )
    async for item in delegate.execute(task, context=context):
        yield item
```

If a sandbox manager currently only looks up sandboxes by definition task id, add a public lookup/reconnect path by `sandbox_id`. Do not force worker construction to know about sandbox registry keys.

- [ ] **Step 6: Run worker contract tests**

Run:

```bash
uv run pytest ergon_core/tests/unit/api/test_worker_contract.py -q
```

Expected: PASS.

---

### Task 8: Update Pydantic Registry To Produce And Publish Component Refs

**Files:**
- Modify: `ergon_core/ergon_core/api/registry.py`
- Test: `ergon_core/tests/unit/registry/test_component_registry.py`

- [ ] **Step 1: Add tests for ref generation and deregistration**

Extend `ergon_core/tests/unit/registry/test_component_registry.py`:

```python
def test_registry_records_import_refs_for_registered_components() -> None:
    registry = ComponentRegistry(catalog_service=ComponentCatalogService())

    registry.register_worker(ExampleWorker.type_slug, ExampleWorker)
    ref = registry.component_refs[("worker", "example-worker")]

    assert ref.kind == "worker"
    assert ref.slug == "example-worker"
    assert ref.module == __name__
    assert ref.qualname == "ExampleWorker"


def test_registry_deregister_removes_component_and_ref() -> None:
    registry = ComponentRegistry(catalog_service=ComponentCatalogService())
    registry.register_worker("example-worker", ExampleWorker)

    registry.deregister("worker", "example-worker")

    assert "example-worker" not in registry.workers
    assert ("worker", "example-worker") not in registry.component_refs
```

- [ ] **Step 2: Run registry tests and verify they fail**

Run:

```bash
uv run pytest ergon_core/tests/unit/registry/test_component_registry.py -q
```

Expected: FAIL because `component_refs` and `deregister` do not exist.

- [ ] **Step 3: Add `ComponentRef` tracking to `ComponentRegistry`**

Modify `ergon_core/ergon_core/api/registry.py`:

```python
from ergon_core.core.application.components.catalog import ComponentCatalogService, ComponentRef
from sqlmodel import Session
```

Add field:

```python
catalog_service: ComponentCatalogService
component_refs: dict[tuple[str, str], ComponentRef] = Field(default_factory=dict)
```

Update register methods to call a private helper after `_register`:

```python
self._remember_ref("worker", slug, worker_cls)
```

Implement:

```python
def deregister(self, kind: str, slug: str) -> None:
    mapping = self._mapping_for(kind)
    mapping.pop(slug, None)
    self.component_refs.pop((kind, slug), None)

def publish(self, session: Session) -> None:
    for ref in self.component_refs.values():
        self.catalog_service.upsert(session, ref)

def _remember_ref(self, kind: str, slug: str, value: object) -> None:
    self.component_refs[(kind, slug)] = ComponentRef(
        kind=kind,
        slug=slug,
        module=value.__module__,
        qualname=value.__qualname__,
    )
```

For worker classes, `__qualname__` is sufficient if the class is module-level. If a value lacks `__module__` or `__qualname__`, raise `ValueError` with a clear message. Do not preserve the old `WorkerFactory` public alias; workers should be registered as importable `Worker` subclasses and constructed by the catalog with only authoring configuration (`name`, `model`, metadata).

Construct the global authoring registry with an explicit service dependency:

```python
registry = ComponentRegistry(catalog_service=ComponentCatalogService())
```

Do not use nullable service parameters or ad hoc fallback construction such as `service or ComponentCatalogService()`. Tests that need isolation should pass their own `ComponentCatalogService()` when constructing a fresh `ComponentRegistry`.

- [ ] **Step 4: Run registry tests**

Run:

```bash
uv run pytest ergon_core/tests/unit/registry/test_component_registry.py -q
```

Expected: PASS.

---

### Task 9: Register Builtins And Smoke Components Into The Catalog

**Files:**
- Modify: `ergon_builtins/ergon_builtins/registry.py`
- Modify: `tests/fixtures/smoke_components/__init__.py`
- Test: `ergon_builtins/tests/unit/registry/test_builtin_pairings.py` or moved equivalent.

- [ ] **Step 1: Add tests that builtins can publish refs into a DB session**

Create or extend builtins registry tests:

```python
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from ergon_core.api.registry import ComponentRegistry
from ergon_core.core.application.components.catalog import ComponentCatalogService


def _session() -> Session:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    return Session(engine)


def test_register_builtins_can_publish_component_refs() -> None:
    from ergon_builtins.registry import register_builtins

    service = ComponentCatalogService()
    registry = ComponentRegistry(catalog_service=service)
    register_builtins(registry)
    session = _session()

    registry.publish(session)
    session.commit()

    ref = service.require(session, kind="worker", slug="training-stub")
    assert ref.module.endswith("training_stub_worker")
    assert ref.qualname == "TrainingStubWorker"
```

- [ ] **Step 2: Run publishing test and verify it fails if refs are incomplete**

Run:

```bash
uv run pytest ergon_builtins/tests/unit/registry -q
```

Expected: PASS if Task 8 is complete; otherwise FAIL on missing refs.

- [ ] **Step 3: Keep publishing explicit and outside registration functions**

Keep registration functions focused on filling the in-process authoring registry:

```python
def register_builtins(target: ComponentRegistry = registry) -> None:
    register_core_builtins(target)
    _register_local_model_builtins()
    _register_data_builtins(target)
```

Do not make builtins import DB/session code. Keep publishing as an explicit caller responsibility:

```python
register_builtins(registry)
with get_session() as session:
    registry.publish(session)
    session.commit()
```

This keeps builtins package independent of persistence.

- [ ] **Step 4: Run builtins registry tests**

Run:

```bash
uv run pytest ergon_builtins/tests/unit/registry -q
```

Expected: PASS.

- [ ] **Step 5: Remove legacy builtins registry dict snapshots**

After publishing tests pass, delete legacy dict snapshot exports from `ergon_builtins/ergon_builtins/registry.py`. The top-level builtins registry module should expose registration functions and install hints only, not old process-local maps.

Remove exports named:

```python
BENCHMARKS
WORKERS
EVALUATORS
SANDBOX_MANAGERS
MODEL_BACKENDS
```

Keep sub-registry implementation details in `registry_core.py` and `registry_data.py` only as inputs to `register_core_builtins()` and `register_data_builtins()`. Update tests/callers that imported top-level dict snapshots to use either `ComponentRegistry` in authoring tests or `ComponentCatalogService` in runtime/catalog tests.

- [ ] **Step 6: Convert worker factory functions to Worker subclasses**

Before publishing worker refs into the catalog, ensure every registered worker slug points at an importable `Worker` subclass. If any existing builtins are module-level factory functions that return workers, replace them with small `Worker` subclasses or move their construction logic into the subclass initializer.

This keeps the public mental model simple:

```python
register_worker("training-stub", TrainingStubWorker)
worker = catalog.build_worker(session, slug="training-stub", name="primary", model="stub:constant")
```

There should be no public `Callable[..., Worker]` / `WorkerFactory` API after this migration.

---

### Task 10: Add Catalog-Only Runtime Loading

**Files:**
- Modify: `ergon_core/ergon_core/core/application/components/catalog.py`
- Modify runtime files listed in file structure.
- Test: core runtime registry tests.

- [ ] **Step 1: Add test for catalog-backed runtime loading**

Create `ergon_core/tests/unit/registry/test_catalog_backed_registry_resolution.py`:

```python
from collections.abc import AsyncGenerator
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from ergon_core.api.benchmark import Task
from ergon_core.api.worker import Worker, WorkerContext, WorkerOutput
from ergon_core.api.worker.worker import WorkerStreamItem
from ergon_core.core.application.components.catalog import ComponentCatalogService, ComponentRef


class CatalogSmokeWorker(Worker):
    type_slug = "catalog-smoke-worker"

    async def execute(
        self,
        task: Task,
        *,
        context: WorkerContext,
    ) -> AsyncGenerator[WorkerStreamItem, None]:
        yield WorkerOutput(output="ok", success=True)


def _session() -> Session:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    return Session(engine)


def test_build_worker_imports_worker_class_without_local_registration() -> None:
    session = _session()
    service = ComponentCatalogService()
    service.upsert(
        session,
        ComponentRef(
            kind="worker",
            slug=CatalogSmokeWorker.type_slug,
            module=__name__,
            qualname="CatalogSmokeWorker",
        ),
    )
    session.commit()

    loaded = service.build_worker(
        session,
        slug=CatalogSmokeWorker.type_slug,
        name="primary",
        model="stub:constant",
    )

    assert isinstance(loaded, CatalogSmokeWorker)
    assert loaded.name == "primary"
```

This test proves the catalog imports the persisted worker class and returns a real `Worker` without requiring process-local registry state or execution-only constructor arguments.

- [ ] **Step 2: Run test and verify it fails**

Run:

```bash
uv run pytest ergon_core/tests/unit/registry/test_catalog_backed_registry_resolution.py -q
```

Expected: FAIL because `build_worker` does not exist yet.

- [ ] **Step 3: Add catalog loading without registry caching**

Do not extend `ComponentRegistry.require_*` into a cache-loading runtime API. Keep `ComponentRegistry` focused on in-process authoring, validation of explicitly registered objects, and publishing refs into the catalog.

Add one generic loading helper to `ComponentCatalogService` for non-worker component types:

```python
def load_ref(self, ref: ComponentRef) -> object:
    return import_component_ref(ref)
```

Runtime code should call catalog resolution directly and not populate `registry.workers`, `registry.benchmarks`, `registry.evaluators`, or `registry.sandbox_managers`.

- [ ] **Step 4: Add typed catalog loading helpers**

Add typed helpers on `ComponentCatalogService` because they make runtime call sites easier to read. Workers should produce a real `Worker`, not a factory/constructor object.

```python
def build_worker(
    self,
    session: Session,
    *,
    slug: str,
    name: str,
    model: str | None,
) -> Worker:
    ref = self.require(session, kind="worker", slug=slug)
    worker_cls = self.load_ref(ref)
    if not isinstance(worker_cls, type) or not issubclass(worker_cls, Worker):
        raise TypeError(
            f"Worker component {slug!r} resolved to {worker_cls!r}, expected a Worker subclass"
        )
    return worker_cls(
        name=name,
        model=model,
        metadata=ref.metadata,
    )

def resolve_benchmark(self, session: Session, slug: str) -> type[Benchmark]:
    return self.load_ref(self.require(session, kind="benchmark", slug=slug))

def resolve_evaluator(self, session: Session, slug: str) -> type[Evaluator]:
    return self.load_ref(self.require(session, kind="evaluator", slug=slug))

def resolve_sandbox_manager(self, session: Session, slug: str) -> type[BaseSandboxManager]:
    return self.load_ref(self.require(session, kind="sandbox_manager", slug=slug))
```

These helpers must still read from Postgres and import the component on each call; do not populate `registry.workers`, `registry.benchmarks`, `registry.evaluators`, or `registry.sandbox_managers`.

- [ ] **Step 5: Run catalog-backed registry tests**

Run:

```bash
uv run pytest ergon_core/tests/unit/registry -q
```

Expected: PASS.

---

### Task 11: Publish Catalog Rows During CLI/API/Test Bootstrap

**Files:**
- Modify: `ergon_cli/ergon_cli/main.py`
- Modify: `ergon_core/ergon_core/core/rest_api/app.py`
- Modify: test setup files.

- [ ] **Step 1: Replace env-var plugin startup with explicit bootstrap helper**

Create a function in a non-core module, for example `ergon_cli/ergon_cli/bootstrap.py`:

```python
"""Process bootstrap for local CLI/API components."""

from ergon_builtins.registry import register_builtins
from ergon_core.api.registry import registry
from ergon_core.core.persistence.shared.db import get_session


def register_and_publish_builtins() -> None:
    register_builtins(registry)
    with get_session() as session:
        registry.publish(session)
        session.commit()
```

- [ ] **Step 2: Call bootstrap from CLI startup**

Modify `ergon_cli/ergon_cli/main.py`:

```python
from ergon_cli.bootstrap import register_and_publish_builtins
```

Call it before command handlers run. If commands like `doctor` should not require DB, skip publishing for those commands by calling it only in experiment/benchmark/eval/workflow handlers.

- [ ] **Step 3: Add API startup bootstrap without env plugins**

Do not import tests from core app. For local Docker, choose one explicit bootstrap:

Option A, if `app.py` is local/dev-only:

```python
from ergon_builtins.registry import register_builtins
from ergon_core.api.registry import registry

register_builtins(registry)
with get_session() as session:
    registry.publish(session)
    session.commit()
```

Option B, if strict core independence is still desired:

Create `ergon_cli/ergon_cli/api_app.py` or a top-level `ergon_app/local_api.py` that imports core `app`, registers/publishes builtins, registers/publishes smoke fixtures, and is the uvicorn target used by docker compose.

Recommendation: use Option B to avoid recreating core-to-builtins coupling.

- [ ] **Step 4: Add smoke publishing in test bootstrap**

For E2E/local Docker, explicit Python bootstrap should call:

```python
from tests.fixtures.smoke_components import register_smoke_components

register_smoke_components(registry)
with get_session() as session:
    registry.publish(session)
    session.commit()
```

Host-side pytest can still call this for in-process tests, but E2E must publish inside the API/Inngest process or before the stack starts against the shared DB.

- [ ] **Step 5: Run CLI/API bootstrap tests**

Run:

```bash
uv run pytest ergon_cli/tests/unit ergon_core/tests/unit/test_app_mounts_harness_conditionally.py -q
```

Expected: PASS after tests are updated for no `ENABLE_TEST_HARNESS`.

---

### Task 12: Update Runtime Jobs To Resolve Through Catalog When Needed

**Files:**
- Modify runtime files listed in file structure.
- Test: existing runtime job tests plus new catalog-backed tests.

- [ ] **Step 1: Update worker execute job**

In `worker_execute.py`, when resolving worker and benchmark:

```python
with get_session() as session:
    worker = catalog.build_worker(
        session,
        slug=payload.worker_type,
        name=payload.assigned_worker_slug,
        model=payload.model_target,
    )
```

Build the `Task` with the runtime graph node identity. Do not derive this from the nullable static definition task id:

```python
if payload.node_id is None:
    raise ContractViolationError("worker-execute requires node_id")

task = Task(
    task_id=payload.node_id,
    task_slug=payload.task_slug,
    instance_key=instance_key,
    description=payload.task_description,
    task_payload=task_payload or EmptyTaskPayload(),
)
```

Build `WorkerContext` without duplicating task identity:

```python
worker_context = WorkerContext(
    run_id=payload.run_id,
    definition_id=payload.definition_id,
    execution_id=payload.execution_id,
    sandbox_id=payload.sandbox_id,
)
```

`WorkerExecuteRequest` should carry only the runtime task id:

```python
node_id: UUID  # runtime task id, always present
```

If worker execution needs static task payload or instance data, resolve it from the persisted graph node:

```python
node = session.get(RunGraphNode, payload.node_id)
if node is None:
    raise ContractViolationError(f"RunGraphNode {payload.node_id} not found")

if node.definition_task_id is not None:
    task_row, instance_row = DefinitionRepository().task_with_instance(
        session,
        node.definition_task_id,
    )
    task_payload = task_row.task_payload_as(benchmark_cls.task_payload_model)
    instance_key = instance_row.instance_key
else:
    task_payload = None
    instance_key = str(payload.node_id)
```

Avoid opening duplicate sessions if the function already opens a session for task rows. Reuse the existing session where practical.

- [ ] **Step 2: Update evaluate task job**

Use:

```python
evaluator_cls = catalog.resolve_evaluator(session, evaluator_type)
benchmark_cls = catalog.resolve_benchmark(session, benchmark_type)
manager_cls = catalog.resolve_sandbox_manager(session, benchmark_type)
```

Do not keep the previous `DefaultSandboxManager` fallback for known benchmark/sandbox slugs. If a persisted benchmark or sandbox slug has no catalog entry, raise immediately; that means definition-time validation or catalog publishing failed.

- [ ] **Step 3: Update sandbox setup and persist outputs**

Use catalog resolution where a sandbox slug is explicit. Do not fall back to `DefaultSandboxManager` for unknown explicit slugs. The purpose of definition-time validation is to prevent unknown slugs from being persisted; if one still reaches runtime, fail loudly with the missing slug and registry/catalog context.

```python
manager_cls = catalog.resolve_sandbox_manager(session, slug)
```

- [ ] **Step 4: Update experiment service and launch**

Resolve benchmark/evaluator via catalog-backed `require_*` using the DB session already used in the service.

- [ ] **Step 5: Update workflow/task validation**

Replace `slug in registry.workers` checks with catalog-backed existence checks:

```python
catalog.require(session, kind="worker", slug=slug)
```

This is the point where cross-process correctness improves: validation no longer depends on the current process having imported builtins first.

- [ ] **Step 6: Run runtime tests**

Run:

```bash
uv run pytest ergon_core/tests/unit/runtime ergon_core/tests/unit/registry -q
```

Expected: PASS.

---

### Task 13: Delete `ERGON_STARTUP_PLUGINS` And `ENABLE_SMOKE_FIXTURES`

**Files:**
- Modify: `ergon_core/ergon_core/core/shared/settings.py`
- Modify: `ergon_core/ergon_core/core/rest_api/app.py`
- Modify: `ergon_cli/ergon_cli/composition/__init__.py`
- Modify: `docker-compose.yml`, `.github/workflows/e2e-benchmarks.yml`, scripts/docs/tests.

- [ ] **Step 1: Add grep-based env-var deletion test**

Create `tests/unit/architecture/test_retired_env_vars.py`:

```python
from pathlib import Path


RETIRED = {
    "ERGON_STARTUP_PLUGINS",
    "ENABLE_SMOKE_FIXTURES",
}


def test_retired_plugin_and_smoke_env_vars_are_not_used_in_code() -> None:
    offenders: list[str] = []
    roots = [Path("ergon_core"), Path("ergon_cli"), Path("ergon_builtins"), Path("tests"), Path("scripts")]
    for root in roots:
        for path in root.rglob("*"):
            if path.is_file() and path.suffix in {".py", ".sh", ".ts", ".tsx", ".yml", ".yaml", ".json"}:
                text = path.read_text(errors="ignore")
                if any(name in text for name in RETIRED):
                    offenders.append(str(path))
    assert offenders == []
```

- [ ] **Step 2: Run env-var deletion test and verify it fails**

Run:

```bash
uv run pytest tests/unit/architecture/test_retired_env_vars.py -q
```

Expected: FAIL listing current usage.

- [ ] **Step 3: Remove startup plugin settings and loader**

Delete from `Settings`:

```python
startup_plugin_specs
startup_plugins
```

Delete `_run_startup_plugins` from `app.py`.

- [ ] **Step 4: Remove `ENABLE_SMOKE_FIXTURES` fallback**

In `ergon_cli/ergon_cli/composition/__init__.py`, delete:

```python
os.environ.get("ENABLE_SMOKE_FIXTURES", ...)
```

Smoke registration should happen through explicit test/bootstrap code, not inside generic CLI composition.

- [ ] **Step 5: Remove env vars from compose/workflows/scripts**

Delete `ERGON_STARTUP_PLUGINS` and `ENABLE_SMOKE_FIXTURES` from:

```text
docker-compose.yml
.github/workflows/e2e-benchmarks.yml
scripts/smoke_local_up.sh
tests/real_llm/benchmarks/test_smoke_stub.py
```

- [ ] **Step 6: Run deletion test**

Run:

```bash
uv run pytest tests/unit/architecture/test_retired_env_vars.py -q
```

Expected: PASS.

---

### Task 14: Delete `ENABLE_TEST_HARNESS` And `TEST_HARNESS_SECRET`

**Files:**
- Modify: `ergon_core/ergon_core/core/shared/settings.py`
- Modify: `ergon_core/ergon_core/core/rest_api/app.py`
- Modify: `ergon_core/ergon_core/core/rest_api/test_harness.py`
- Modify dashboard test clients/routes referencing `TEST_HARNESS_SECRET`.
- Modify compose/workflows/package scripts/docs.

- [ ] **Step 1: Extend retired env-var test**

Add to `RETIRED`:

```python
"ENABLE_TEST_HARNESS",
"TEST_HARNESS_SECRET",
```

Run:

```bash
uv run pytest tests/unit/architecture/test_retired_env_vars.py -q
```

Expected: FAIL listing all remaining uses.

- [ ] **Step 2: Always mount test harness under a danger-prefixed route**

Change test harness router:

```python
router = APIRouter(prefix="/api/__danger__/test-harness", tags=["danger-test-harness"])
```

Update all clients from `/api/test/...` to `/api/__danger__/test-harness/...`.

- [ ] **Step 3: Remove secret requirement from write endpoints**

Delete `_require_secret` from `test_harness.py`.

Remove `x_test_secret` parameters and `_require_secret(x_test_secret)` calls from:

```python
seed_run
reset_test_rows
```

Decide whether `submit_cohort` should remain write-but-unguarded; with the danger-prefixed route, it should also be under the same unauthenticated local harness policy.

- [ ] **Step 4: Remove conditional mount**

In `app.py`, replace:

```python
if settings.enable_test_harness:
    app.include_router(_test_harness_router)
```

with:

```python
app.include_router(_test_harness_router)
```

Delete `enable_test_harness` from `Settings`.

- [ ] **Step 5: Update dashboard and Python clients**

Update:

```text
ergon-dashboard/tests/helpers/backendHarnessClient.ts
ergon-dashboard/src/app/api/test/dashboard/seed/route.ts
ergon-dashboard/src/lib/config.ts
tests/e2e/_asserts.py
tests/e2e/test_*_smoke.py
tests/integration/smokes/test_smoke_harness.py
package.json
scripts/smoke_local_run.sh
```

Remove `X-Test-Secret` headers and env lookups. Update URL paths to danger-prefixed harness routes.

- [ ] **Step 6: Update tests for always-mounted harness**

Replace `test_app_mounts_harness_conditionally.py` with a test named:

```python
def test_app_mounts_danger_test_harness_routes() -> None:
    routes = {route.path for route in app.routes}
    assert "/api/__danger__/test-harness/read/run/{run_id}/state" in routes
```

- [ ] **Step 7: Run retired env-var test**

Run:

```bash
uv run pytest tests/unit/architecture/test_retired_env_vars.py -q
```

Expected: PASS.

---

### Task 15: Verification

**Files:**
- No planned source files beyond fixes revealed by tests.

- [ ] **Step 1: Verify retired env vars are gone**

Run:

```bash
rg "ENABLE_TEST_HARNESS|TEST_HARNESS_SECRET|ERGON_STARTUP_PLUGINS|ENABLE_SMOKE_FIXTURES|ERGON_SKIP_INFRA_CHECK" ergon_core ergon_builtins ergon_cli tests scripts docker-compose.yml .github package.json ergon-dashboard -n
```

Expected: no matches, except historical docs if the team chooses not to update old planning documents. The architecture test should search code/config, not historical plans.

- [ ] **Step 2: Verify component catalog migration imports**

Run:

```bash
uv run alembic -c ergon_core/alembic.ini upgrade head
```

Expected: migration succeeds on a local/dev DB.

- [ ] **Step 3: Run package-owned unit tests**

Run:

```bash
uv run pytest ergon_core/tests/unit ergon_builtins/tests/unit ergon_cli/tests/unit tests/unit -q
```

Expected: PASS.

- [ ] **Step 4: Run backend unit script**

Run:

```bash
pnpm run test:be:unit
```

Expected: PASS.

- [ ] **Step 5: Run E2E collection**

Run:

```bash
uv run pytest tests/e2e --collect-only -q
```

Expected: PASS.

- [ ] **Step 6: Run lint on changed Python paths**

Run:

```bash
uv run ruff check ergon_core ergon_builtins ergon_cli tests scripts
```

Expected: PASS.

---

## Self-Review

- Spec coverage: The plan covers package-owned test layout, PG component catalog schema, catalog service, registry publishing/loading, runtime refactor, and deletion of all five env vars named in the discussion.
- Placeholder scan: The plan contains no placeholder instructions. The migration revision id must be chosen from the actual Alembic head during execution, and the plan explicitly instructs how to do that.
- Type consistency: The same names are used throughout: `ComponentCatalogEntry`, `ComponentCatalogService`, `ComponentRef`, `component_catalog`, `registry.publish`, and catalog-backed `require_*` methods.
