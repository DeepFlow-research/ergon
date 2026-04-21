---
status: active
opened: 2026-04-17
author: deepflow-research
architecture_refs: [docs/architecture/02_runtime_lifecycle.md#invariants, docs/architecture/04_persistence.md#core-abstractions]
supersedes: []
superseded_by: null
---

# RFC: Delete `RunTaskStateEvent` and its legacy queries

## Problem

`RunTaskStateEvent` (`ergon_core/ergon_core/core/persistence/telemetry/models.py:243–278`)
is the legacy append-only WAL for task status transitions. It was superseded by
`RunGraphMutation` (`ergon_core/ergon_core/core/persistence/graph/models.py:174–187`),
which is a strict superset of the same data plus monotonic `sequence` per run. Two
sources of truth is a maintenance hazard: every contributor reading the persistence
layer must trace the abandoned table, confirm it is abandoned, and then internalise
"ignore this".

**What exists today:**

- `RunTaskStateEvent` is defined at `telemetry/models.py:243` with five columns:
  `run_id`, `definition_task_id`, `task_execution_id`, `event_type`,
  `old_status`, `new_status`, `event_metadata`, `created_at`. A `model_validator`
  (`_validate_event_metadata`) exists at line 276.
- `propagation.py` (line 7) declares: `"RunTaskStateEvent is no longer written or
  read by this module."` No write site exists anywhere in the codebase.
- `StateEventsQueries` at `persistence/queries.py:266–307` is the last reader.
  It exposes four methods (`list_by_run`, `get_by_task`, `get_latest_status`,
  `get_by_event_type`) wired into the `Queries` singleton at line 475/483. Nothing
  calls `queries.state_events.*` anywhere in the runtime (verified by grep).
- The `Queries` singleton at `queries.py:469–488` exposes `state_events:
  StateEventsQueries` as a named attribute, so any contributor who reads the
  singleton's fields will see this as a live entry point.
- Three test files import or reference `RunTaskStateEvent`:
  - `tests/state/test_type_invariants.py:25` — imports and constructs
    `RunTaskStateEvent` to verify enum constraints.
  - `tests/state/test_type_invariants.py:53–71` — `TestRunTaskStateEventTypes`
    class with two test methods.
  - `tests/state/test_propagation.py:225` — docstring mentions
    `RunTaskStateEvent` in a test class verifying writes go to `RunGraphNode`,
    not `RunTaskStateEvent`.
- `docs/event-wal/STATE_UNIFICATION_PLAN.md` documents the migration to graph WAL
  and lists `RunTaskStateEvent` write sites (now all gone).
- `docs/TY_PASS_PLAN.md` lists `RunTaskStateEvent.task_execution_id` in the
  nullable-field audit (Category G.4, correctly optional).
- `docs/architecture/04_persistence.md` §4 has the invariant: "**`RunTaskStateEvent`
  is frozen.** No new writes. Reads permitted only for legacy-run rehydration."
  §7 has the follow-up: "An RFC is in flight to remove the legacy table outright."
- `docs/architecture/02_runtime_lifecycle.md` §4.1 (Known limits) has:
  "`RunTaskStateEvent` is deprecated and unread. [...] `StateEventsQueries` is the
  last reader and goes away with the table in this RFC."
- The table was created in the initial schema migration
  `5f01559f2bc3_initial_schema_v2.py` (revision `5f01559f2bc3`). The current
  head of the migration chain is `b5b36e45e5e6_add_containment_and_cancelled.py`
  (`down_revision = "f9075c2ddbc9"`).

The cost of leaving this in place is real. The `Queries` singleton surfaces
`state_events` as a live entry point; `test_type_invariants.py` keeps the class
exercised; the architecture docs carry two clauses that are strictly false (there
is no rehydration use of this table). The longer this sits, the more likely a
contributor wires a new reader against it.

## Proposal

Six changes, ordered to guarantee no races:

1. **Data export** — before the drop, stream any remaining rows to
   `exports/run_task_state_events_<timestamp>.jsonl.gz` via a checked-in
   one-shot script (`scripts/export_run_task_state_events.py`). The script
   runs as part of the deploy that applies the Alembic migration.
2. **Alembic revision** — new revision dropping `run_task_state_events` and
   its three indexes (`ix_run_task_state_events_run_id`,
   `ix_run_task_state_events_event_type`,
   `ix_run_task_state_events_definition_task_id`). The revision also drops the
   `experimentcohortstatus`-family Postgres enum if still owned by this table
   (verify in migration autogen — `old_status`/`new_status` are `TaskExecutionStatus`,
   not a named enum). `down_revision` must point to `b5b36e45e5e6`.
3. **Delete `RunTaskStateEvent` model** and `_validate_event_metadata` validator
   (`telemetry/models.py:239–278`). Drop the import of `RunTaskStateEvent` from
   `queries.py:30`.
4. **Delete `StateEventsQueries`** (`queries.py:266–307`) and remove
   `state_events: StateEventsQueries` from the `Queries` class (lines 475/483).
5. **Purge test references** — remove `TestRunTaskStateEventTypes` and the
   `RunTaskStateEvent` import from `test_type_invariants.py`; update the
   `TestGraphStateVerification` docstring in `test_propagation.py`.
6. **Update docs** — delete `docs/event-wal/STATE_UNIFICATION_PLAN.md`,
   prune `RunTaskStateEvent` references from `docs/event-wal/01_AUDIT.md` and
   `docs/event-wal/02_INCREMENTAL_PERSISTENCE.md`, remove the nullable audit row
   from `docs/TY_PASS_PLAN.md`, and update architecture docs (see §Invariants
   affected).
7. **Sentinel test** — add `tests/state/test_legacy_wal_absent.py` asserting the
   table does not appear in `pg_tables`.

The Alembic drop must precede the model deletion commit so that `alembic
autogenerate` does not race against a missing SQLModel class. In practice the
drop revision and model deletion land in the same PR, with the migration script
committed first.

## Architecture overview

### Before

```
persistence/queries.py
  Queries.state_events: StateEventsQueries   ← orphaned; nothing calls it
  StateEventsQueries                         ← wraps RunTaskStateEvent
      list_by_run()
      get_by_task()
      get_latest_status()
      get_by_event_type()

persistence/telemetry/models.py
  RunTaskStateEvent                          ← table: run_task_state_events
      id, run_id, definition_task_id,
      task_execution_id, event_type,
      old_status, new_status,
      event_metadata, created_at
  _validate_event_metadata                   ← model_validator

DB schema
  run_task_state_events (0 new writes since propagation.py refactor)
  ix_run_task_state_events_run_id
  ix_run_task_state_events_event_type
  ix_run_task_state_events_definition_task_id

Single source of truth for task state:
  RunGraphMutation  ← append-only, monotonic sequence
  RunGraphNode      ← mutable status cache
```

### After

```
persistence/queries.py
  Queries (no state_events attribute)        ← leaner singleton

persistence/telemetry/models.py
  (RunTaskStateEvent deleted)

DB schema
  (run_task_state_events table gone)
  (three indexes gone)

Single source of truth for task state:
  RunGraphMutation  ← unchanged, still canonical
  RunGraphNode      ← unchanged
```

### Data flow (no change to runtime)

The runtime never wrote to `run_task_state_events` after the propagation
refactor. The data flow through `WorkflowGraphRepository` →
`RunGraphMutation` / `RunGraphNode` is unchanged by this RFC. Removing the
table removes dead weight, not any live path.

## Type / interface definitions

No new types. The following types are **deleted**:

```python
# DELETED FROM: ergon_core/ergon_core/core/persistence/telemetry/models.py
# Lines 239–278

# ---------------------------------------------------------------------------
# RunTaskStateEvent
# ---------------------------------------------------------------------------

class RunTaskStateEvent(SQLModel, table=True):
    __tablename__ = "run_task_state_events"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    run_id: UUID = Field(foreign_key="runs.id", index=True)
    definition_task_id: UUID = Field(
        foreign_key="experiment_definition_tasks.id",
        index=True,
    )
    task_execution_id: UUID | None = Field(
        default=None,
        foreign_key="run_task_executions.id",
    )
    event_type: str = Field(
        default="state_change", index=True
    )
    old_status: TaskExecutionStatus | None = None
    new_status: TaskExecutionStatus
    event_metadata: dict = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=_utcnow, sa_type=TZDateTime)

    def parsed_event_metadata(self) -> dict[str, object]: ...
    @classmethod
    def _parse_event_metadata(cls, data: dict) -> dict[str, object]: ...
    @model_validator(mode="after")
    def _validate_event_metadata(self) -> "RunTaskStateEvent": ...
```

```python
# DELETED FROM: ergon_core/ergon_core/core/persistence/queries.py
# Lines 266–307, and the state_events attribute at 475/483

class StateEventsQueries(BaseQueries[RunTaskStateEvent]):
    def __init__(self) -> None: ...
    def list_by_run(self, run_id: UUID) -> list[RunTaskStateEvent]: ...
    def get_by_task(self, run_id: UUID, definition_task_id: UUID) -> list[RunTaskStateEvent]: ...
    def get_latest_status(self, run_id: UUID, definition_task_id: UUID) -> str | None: ...
    def get_by_event_type(self, run_id: UUID, event_type: str) -> list[RunTaskStateEvent]: ...
```

## New files

### `scripts/export_run_task_state_events.py`

```python
# scripts/export_run_task_state_events.py
"""One-shot export of run_task_state_events rows to JSONL.gz.

Run BEFORE applying the Alembic migration that drops the table.

Usage:
    uv run python scripts/export_run_task_state_events.py

Output: exports/run_task_state_events_<ISO8601_timestamp>.jsonl.gz

The archive is insurance. Most systems have 0 rows since propagation.py
stopped writing to this table. The script is idempotent — running it twice
produces two archive files; the table is not modified.
"""

from __future__ import annotations

import gzip
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

# Ensure ergon_core is importable when run from the repo root.
sys.path.insert(0, str(Path(__file__).parent.parent))

from ergon_core.core.persistence.shared.db import get_session
from ergon_core.core.persistence.telemetry.models import RunTaskStateEvent
from sqlmodel import select


def main() -> None:
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    exports_dir = Path(__file__).parent.parent / "exports"
    exports_dir.mkdir(exist_ok=True)
    out_path = exports_dir / f"run_task_state_events_{timestamp}.jsonl.gz"

    row_count = 0
    with gzip.open(out_path, "wt", encoding="utf-8") as fh:
        with get_session() as session:
            stmt = select(RunTaskStateEvent).order_by(RunTaskStateEvent.created_at)
            for row in session.exec(stmt):
                fh.write(
                    json.dumps(
                        {
                            "id": str(row.id),
                            "run_id": str(row.run_id),
                            "definition_task_id": str(row.definition_task_id),
                            "task_execution_id": str(row.task_execution_id)
                            if row.task_execution_id
                            else None,
                            "event_type": row.event_type,
                            "old_status": row.old_status,
                            "new_status": row.new_status,
                            "event_metadata": row.event_metadata,
                            "created_at": row.created_at.isoformat(),
                        }
                    )
                    + "\n"
                )
                row_count += 1

    print(f"Exported {row_count} rows to {out_path}")


if __name__ == "__main__":
    main()
```

### `ergon_core/migrations/versions/<revision_id>_drop_run_task_state_events.py`

The revision ID is generated by `alembic revision --autogenerate`. The template
below shows the expected structure; the implementer must run autogenerate (or
author by hand) after deleting the `RunTaskStateEvent` model so that Alembic
detects the table removal.

```python
# ergon_core/migrations/versions/<rev>_drop_run_task_state_events.py
"""drop run_task_state_events table

Revision ID: <generated>
Revises: b5b36e45e5e6
Create Date: <generated>

Drops the legacy RunTaskStateEvent table and its three indexes.
Data was exported to exports/run_task_state_events_<timestamp>.jsonl.gz
before this migration ran.
"""

from typing import Sequence, Union

import sqlalchemy as sa
import sqlmodel
from alembic import op

revision: str = "<generated>"
down_revision: Union[str, None] = "b5b36e45e5e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_index(
        op.f("ix_run_task_state_events_definition_task_id"),
        table_name="run_task_state_events",
    )
    op.drop_index(
        op.f("ix_run_task_state_events_event_type"),
        table_name="run_task_state_events",
    )
    op.drop_index(
        op.f("ix_run_task_state_events_run_id"),
        table_name="run_task_state_events",
    )
    op.drop_table("run_task_state_events")


def downgrade() -> None:
    op.create_table(
        "run_task_state_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("definition_task_id", sa.Uuid(), nullable=False),
        sa.Column("task_execution_id", sa.Uuid(), nullable=True),
        sa.Column("event_type", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("old_status", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("new_status", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("event_metadata", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["definition_task_id"], ["experiment_definition_tasks.id"]),
        sa.ForeignKeyConstraint(["run_id"], ["runs.id"]),
        sa.ForeignKeyConstraint(["task_execution_id"], ["run_task_executions.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_run_task_state_events_run_id"),
        "run_task_state_events",
        ["run_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_run_task_state_events_event_type"),
        "run_task_state_events",
        ["event_type"],
        unique=False,
    )
    op.create_index(
        op.f("ix_run_task_state_events_definition_task_id"),
        "run_task_state_events",
        ["definition_task_id"],
        unique=False,
    )
```

### `tests/state/test_legacy_wal_absent.py`

```python
# tests/state/test_legacy_wal_absent.py
"""Sentinel: run_task_state_events must not exist in the schema.

If someone re-introduces the table by copy-paste, this test fails immediately
in CI. The check runs against the same test DB used by all other state tests
(SQLite in tests, Postgres in integration).
"""

from sqlmodel import Session, text


def test_run_task_state_events_table_absent(session: Session) -> None:
    """The legacy table must not exist in the current schema."""
    # Works for both Postgres and SQLite.
    # Postgres: pg_tables is a system catalog view.
    # SQLite: sqlite_master is the schema table.
    try:
        # Postgres path
        result = session.exec(
            text(
                "SELECT tablename FROM pg_tables "
                "WHERE schemaname = 'public' "
                "AND tablename = 'run_task_state_events'"
            )
        ).all()
        assert result == [], (
            "run_task_state_events still exists in pg_tables — "
            "migration not applied or table re-created."
        )
    except Exception:
        # SQLite path (test environment)
        result = session.exec(
            text(
                "SELECT name FROM sqlite_master "
                "WHERE type='table' AND name='run_task_state_events'"
            )
        ).all()
        assert result == [], (
            "run_task_state_events still exists in sqlite_master — "
            "SQLModel still has table=True for RunTaskStateEvent."
        )
```

## Exact diffs for modified files

### `ergon_core/ergon_core/core/persistence/telemetry/models.py`

```diff
-# ---------------------------------------------------------------------------
-# RunTaskStateEvent
-# ---------------------------------------------------------------------------
-
-
-class RunTaskStateEvent(SQLModel, table=True):
-    __tablename__ = "run_task_state_events"
-
-    id: UUID = Field(default_factory=uuid4, primary_key=True)
-    run_id: UUID = Field(foreign_key="runs.id", index=True)
-    definition_task_id: UUID = Field(
-        foreign_key="experiment_definition_tasks.id",
-        index=True,
-    )
-    task_execution_id: UUID | None = Field(
-        default=None,
-        foreign_key="run_task_executions.id",
-    )
-    event_type: str = Field(
-        default="state_change", index=True
-    )  # Literal["state_change"] — str for SQLModel compat
-    old_status: TaskExecutionStatus | None = None
-    new_status: TaskExecutionStatus
-    event_metadata: dict = Field(default_factory=dict, sa_column=Column(JSON))
-    created_at: datetime = Field(default_factory=_utcnow, sa_type=TZDateTime)
-
-    # -- JSON accessor: event_metadata --
-
-    def parsed_event_metadata(self) -> dict[str, object]:
-        return self.__class__._parse_event_metadata(self.event_metadata)
-
-    @classmethod
-    def _parse_event_metadata(cls, data: dict) -> dict[str, object]:
-        if not isinstance(data, dict):
-            raise ValueError(f"event_metadata must be a dict, got {type(data).__name__}")
-        return data
-
-    @model_validator(mode="after")
-    def _validate_event_metadata(self) -> "RunTaskStateEvent":
-        self.__class__._parse_event_metadata(self.event_metadata)
-        return self
-
-
 # ---------------------------------------------------------------------------
 # RunTaskEvaluation
 # ---------------------------------------------------------------------------
```

The `model_validator` import at the top of `models.py` (`from pydantic import
model_validator`) must be retained — other models in the same file use it
(`RunRecord._validate_summary_json`, `RunTaskExecution._validate_output_json`,
etc.). No import change needed.

### `ergon_core/ergon_core/core/persistence/queries.py`

```diff
 from ergon_core.core.persistence.telemetry.models import (
     RunRecord,
     RunResource,
     RunTaskEvaluation,
     RunTaskExecution,
-    RunTaskStateEvent,
 )
```

```diff
-# ---------------------------------------------------------------------------
-# State Events
-# ---------------------------------------------------------------------------
-
-
-class StateEventsQueries(BaseQueries[RunTaskStateEvent]):
-    def __init__(self) -> None:
-        super().__init__(RunTaskStateEvent)
-
-    def list_by_run(self, run_id: UUID) -> list[RunTaskStateEvent]:
-        with get_session() as session:
-            stmt = (
-                select(RunTaskStateEvent)
-                .where(RunTaskStateEvent.run_id == run_id)
-                .order_by(RunTaskStateEvent.created_at)
-            )
-            return list(session.exec(stmt).all())
-
-    def get_by_task(self, run_id: UUID, definition_task_id: UUID) -> list[RunTaskStateEvent]:
-        with get_session() as session:
-            stmt = (
-                select(RunTaskStateEvent)
-                .where(
-                    RunTaskStateEvent.run_id == run_id,
-                    RunTaskStateEvent.definition_task_id == definition_task_id,
-                )
-                .order_by(RunTaskStateEvent.created_at)
-            )
-            return list(session.exec(stmt).all())
-
-    def get_latest_status(self, run_id: UUID, definition_task_id: UUID) -> str | None:
-        events = self.get_by_task(run_id, definition_task_id)
-        if not events:
-            return None
-        return events[-1].new_status
-
-    def get_by_event_type(self, run_id: UUID, event_type: str) -> list[RunTaskStateEvent]:
-        with get_session() as session:
-            stmt = (
-                select(RunTaskStateEvent)
-                .where(
-                    RunTaskStateEvent.run_id == run_id,
-                    RunTaskStateEvent.event_type == event_type,
-                )
-                .order_by(RunTaskStateEvent.created_at)
-            )
-            return list(session.exec(stmt).all())
-
-
 # ---------------------------------------------------------------------------
 # Evaluations
 # ---------------------------------------------------------------------------
```

```diff
 class Queries:
     """Namespace singleton providing typed query methods for all tables."""

     runs: RunsQueries
     definitions: DefinitionsQueries
     task_executions: TaskExecutionsQueries
-    state_events: StateEventsQueries
     evaluations: EvaluationsQueries
     resources: ResourcesQueries

     def __init__(self) -> None:
         self.runs = RunsQueries()
         self.definitions = DefinitionsQueries()
         self.task_executions = TaskExecutionsQueries()
-        self.state_events = StateEventsQueries()
         self.evaluations = EvaluationsQueries()
         self.resources = ResourcesQueries()
```

### `tests/state/test_type_invariants.py`

```diff
 from ergon_core.core.persistence.telemetry.models import (
     ExperimentCohort,
     ExperimentCohortStatus,
     RunGenerationTurn,
     RunRecord,
     RunResource,
     RunTaskExecution,
-    RunTaskStateEvent,
     TrainingSession,
 )
```

```diff
-class TestRunTaskStateEventTypes:
-    def test_accepts_valid_event_type(self):
-        event = RunTaskStateEvent(
-            run_id=uuid4(),
-            definition_task_id=uuid4(),
-            event_type="state_change",
-            new_status=TaskExecutionStatus.COMPLETED,
-        )
-        assert event.event_type == "state_change"
-
-    def test_accepts_valid_old_status(self):
-        event = RunTaskStateEvent(
-            run_id=uuid4(),
-            definition_task_id=uuid4(),
-            event_type="state_change",
-            old_status=TaskExecutionStatus.PENDING,
-            new_status=TaskExecutionStatus.RUNNING,
-        )
-        assert event.old_status == TaskExecutionStatus.PENDING
-
-
 class TestExperimentCohortStatus:
```

### `tests/state/test_propagation.py` (docstring only)

```diff
 class TestGraphStateVerification:
-    """Verify that state is written to RunGraphNode and RunGraphMutation,
-    not to RunTaskStateEvent."""
+    """Verify that state is written to RunGraphNode and RunGraphMutation."""
```

## Implementation order

### Phase 1 — Pre-flight and data export (single PR)

| Step | What | Files touched |
|---|---|---|
| 1 | Write and commit `scripts/export_run_task_state_events.py` | ADD `scripts/export_run_task_state_events.py` |
| 2 | Run the export script locally and commit any resulting archive to `exports/` (or document that it produced 0 rows) | ADD `exports/run_task_state_events_<ts>.jsonl.gz` (if non-empty) |
| 3 | Write the pre-migration audit script (inline in PR description) checking that every `run_task_state_events` row has a corresponding `run_graph_mutations` entry for the same `run_id` / `definition_task_id` status transition. Note result. | (no file; inline check) |

### Phase 2 — Schema drop (single PR, merges after Phase 1)

| Step | What | Files touched |
|---|---|---|
| 4 | Delete `RunTaskStateEvent` class from `telemetry/models.py` (lines 239–278) | MODIFY `ergon_core/ergon_core/core/persistence/telemetry/models.py` |
| 5 | Run `alembic revision --autogenerate -m "drop_run_task_state_events"` to produce the migration; verify it contains only `drop_table` + three `drop_index`; set `down_revision = "b5b36e45e5e6"` | ADD `ergon_core/migrations/versions/<rev>_drop_run_task_state_events.py` |
| 6 | Delete `RunTaskStateEvent` import and `StateEventsQueries` class from `queries.py`; remove `state_events` from `Queries.__init__` | MODIFY `ergon_core/ergon_core/core/persistence/queries.py` |
| 7 | Remove `TestRunTaskStateEventTypes` and `RunTaskStateEvent` import from `test_type_invariants.py` | MODIFY `tests/state/test_type_invariants.py` |
| 8 | Update docstring in `test_propagation.py:225` | MODIFY `tests/state/test_propagation.py` |
| 9 | Add sentinel test `test_legacy_wal_absent.py` | ADD `tests/state/test_legacy_wal_absent.py` |

### Phase 3 — Docs cleanup (same PR as Phase 2 or immediate follow-up)

| Step | What | Files touched |
|---|---|---|
| 10 | Delete `docs/event-wal/STATE_UNIFICATION_PLAN.md` | DELETE `docs/event-wal/STATE_UNIFICATION_PLAN.md` |
| 11 | Prune `RunTaskStateEvent` references in `docs/event-wal/01_AUDIT.md` (§2 tables, §4.2 fix options) and `docs/event-wal/02_INCREMENTAL_PERSISTENCE.md` (§6.3 type-tightening list, §14 MODIFY block) | MODIFY `docs/event-wal/01_AUDIT.md`, `docs/event-wal/02_INCREMENTAL_PERSISTENCE.md` |
| 12 | Remove `RunTaskStateEvent.task_execution_id` row from `docs/TY_PASS_PLAN.md` §G.4 table | MODIFY `docs/TY_PASS_PLAN.md` |
| 13 | Update `docs/architecture/02_runtime_lifecycle.md` and `docs/architecture/04_persistence.md` (see §Invariants affected) | MODIFY both architecture docs |

## File map

### ADD

| File | Purpose |
|---|---|
| `scripts/export_run_task_state_events.py` | One-shot JSONL.gz export before table drop |
| `exports/run_task_state_events_<ts>.jsonl.gz` | Archive of any remaining rows (may be 0 bytes) |
| `ergon_core/migrations/versions/<rev>_drop_run_task_state_events.py` | Alembic revision dropping `run_task_state_events` and its three indexes; `down_revision = "b5b36e45e5e6"` |
| `tests/state/test_legacy_wal_absent.py` | Sentinel asserting `run_task_state_events` is absent from `pg_tables` / `sqlite_master` |

### MODIFY

| File | Changes |
|---|---|
| `ergon_core/ergon_core/core/persistence/telemetry/models.py` | Delete lines 239–278: `RunTaskStateEvent` class and `_validate_event_metadata` validator |
| `ergon_core/ergon_core/core/persistence/queries.py` | Delete import of `RunTaskStateEvent` (line 30); delete `StateEventsQueries` class (lines 266–307); remove `state_events` attribute from `Queries` class (lines 475/483) |
| `tests/state/test_type_invariants.py` | Remove `RunTaskStateEvent` import (line 25); remove `TestRunTaskStateEventTypes` class (lines 53–71) |
| `tests/state/test_propagation.py` | Update `TestGraphStateVerification` docstring at line 225 |
| `docs/event-wal/01_AUDIT.md` | Prune §2 tables and §4.2 describing `RunTaskStateEvent` write sites (now historical) |
| `docs/event-wal/02_INCREMENTAL_PERSISTENCE.md` | Remove `RunTaskStateEvent` from §6.3 type-tightening list and §14 MODIFY block |
| `docs/TY_PASS_PLAN.md` | Remove `RunTaskStateEvent.task_execution_id` row from §G.4 table |
| `docs/architecture/02_runtime_lifecycle.md` | See §Invariants affected |
| `docs/architecture/04_persistence.md` | See §Invariants affected |

### DELETE

| File | Reason |
|---|---|
| `docs/event-wal/STATE_UNIFICATION_PLAN.md` | The migration plan it describes is now complete; keeping it creates false impression of in-flight work |

## Testing approach

### Unit — `test_type_invariants.py` (post-removal)

After removing `TestRunTaskStateEventTypes`, the remaining test coverage in
`test_type_invariants.py` verifies `RunRecord`, `RunTaskExecution`,
`ExperimentCohort`, `RunGenerationTurn`, etc. No regression to existing tests.

No replacement test needed for `RunTaskStateEvent` construction — the class
no longer exists. Any attempt to import or instantiate it after removal will
fail at import time (module error), not silently.

### Sentinel — `test_legacy_wal_absent.py`

```python
# tests/state/test_legacy_wal_absent.py

def test_run_task_state_events_table_absent(session: Session) -> None:
    """Locks the removal: if the table is re-created, CI fails immediately."""
    try:
        result = session.exec(
            text(
                "SELECT tablename FROM pg_tables "
                "WHERE schemaname = 'public' "
                "AND tablename = 'run_task_state_events'"
            )
        ).all()
        assert result == []
    except Exception:
        result = session.exec(
            text(
                "SELECT name FROM sqlite_master "
                "WHERE type='table' AND name='run_task_state_events'"
            )
        ).all()
        assert result == []
```

**Note on SQLite test environment:** The sentinel uses a `try/except` to handle
both Postgres (CI/integration) and SQLite (fast unit tests). Verify that
`conftest.py` in `tests/state/` provides a `session` fixture compatible with
this approach. If the test session uses a SQLite backend (likely, given the
fast test suite design), the `except` branch handles it.

### Integration — migration correctness

After applying the migration against a Postgres instance seeded with the
initial schema, confirm:

1. `\d run_task_state_events` in psql returns "did not find any relation named".
2. `alembic current` reports the new revision as head.
3. `alembic downgrade -1` restores the table (the `downgrade()` function is
   provided in the revision).

### Pre-migration audit (one-time, not automated)

Before running in any environment with real data, run:

```python
# Inline check — run in a migration script or psql session
SELECT
    COUNT(*) AS state_event_rows,
    COUNT(DISTINCT run_id) AS affected_runs
FROM run_task_state_events;
```

If this returns non-zero, run the export script first and verify the archive
before dropping. If zero, proceed directly to the migration.

## Trace / observability impact

None. `run_task_state_events` is not referenced by any span, metric, or log
emitter. No dashboard query reads from it. No trace attribute is sourced from
it. Removing the table and its queries is invisible to all observability paths.

## Risks and mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Unreconciled rows in `run_task_state_events` | Historical state lost without archive | Export script runs before migration; pre-migration row-count audit catches non-zero cases |
| Another module imports `RunTaskStateEvent` (missed by grep) | Import error at runtime after model deletion | `ruff check` + `ty check` catch all import references at CI time; grep confirms no callers today |
| `Queries.state_events` referenced by a downstream consumer (e.g. dashboard, CLI) | `AttributeError` at runtime | Grep confirms no callers of `queries.state_events.*` anywhere; sentinel test locks the removal |
| `alembic downgrade` needed after deploy | Table re-created but model class gone | `downgrade()` in the revision re-creates the table DDL without SQLModel; the class is recoverable from git history |
| SQLite schema for fast tests still registers the `RunTaskStateEvent` table | `test_legacy_wal_absent.py` passes for wrong reason | The sentinel uses `sqlite_master` for SQLite environments; removing `table=True` from the class prevents SQLite table creation entirely |
| `model_validator` import becomes unused after deletion | Ruff `F401` error in CI | Verified: `RunRecord`, `RunTaskExecution`, `RunResource`, `ExperimentCohort` all use `@model_validator`; import remains live |

## Invariants affected

### `docs/architecture/02_runtime_lifecycle.md`

**§4 Invariants (Known limits):**

Remove the following bullet entirely:

> "**`RunTaskStateEvent` is deprecated and unread.** Propagation no longer
> writes to it (`propagation.py:7-8`). `StateEventsQueries` is the last reader
> and goes away with the table in `docs/rfcs/active/2026-04-17-delete-run-task-state-event.md`.
> New code must read state from `RunGraphNode` via `GraphNodeLookup`."

After merge, the table is gone; the sentence becomes a dead reference.

**§7 Follow-ups:**

Remove the line:

> "`docs/rfcs/active/2026-04-17-delete-run-task-state-event.md` — drop the
> deprecated `RunTaskStateEvent` table and the last reader in `StateEventsQueries`."

**§6 Anti-patterns:**

The existing anti-pattern entry "Direct DB writes to `RunGraphNode.status`"
and related entries are unaffected. No new anti-pattern entry needed — the
deletion is the enforcement.

### `docs/architecture/04_persistence.md`

**§2 Core abstractions:**

Remove or update the following paragraph:

> "**`RunTaskStateEvent` is legacy.** The table is frozen. New code MUST NOT
> read or write it; rehydration of legacy runs is the only permitted read."

After merge, replace with:

> "**`RunTaskStateEvent` is deleted.** The table was dropped in migration
> `<rev>_drop_run_task_state_events`. Any historical data was archived to
> `exports/run_task_state_events_<ts>.jsonl.gz` before the drop."

**§4 Invariants:**

Remove the bullet:

> "**`RunTaskStateEvent` is frozen.** No new writes. Reads permitted only
> for legacy-run rehydration. New code uses the mutation log plus node
> status instead."

**§6 Anti-patterns:**

Remove the bullet:

> "**Writing to `RunTaskStateEvent`.** The table is frozen legacy. Any new
> write is a regression; use the mutation log plus node status."

**§7 Follow-ups:**

Remove the entry:

> "**`RunTaskStateEvent` deletion.** An RFC is in flight to remove the legacy
> table outright. Until it lands, the frozen-table invariant stands; on merge,
> drop the legacy entry from §2 and the matching anti-pattern bullet."

## Alternatives considered

- **Keep the table, make the queries harder to reach.** Rejected: dead weight
  in the schema. Every contributor still has to understand why it's there.
- **Keep the model as a historical data-read adapter.** Rejected: nobody reads
  it today; if a later need arises, we can bring back a read-only JSON archive
  consumer against the `.jsonl.gz` file.
- **Migrate existing rows into `RunGraphMutation` instead of archiving.**
  Rejected: the mutation log has different invariants (monotonic sequence per
  run, actor, reason); fabricating those for legacy rows pollutes the WAL.
- **Soft-delete by setting `table=False` on the SQLModel class.** Rejected:
  leaves the table in the DB schema indefinitely; Alembic autogenerate would
  detect and re-propose the drop on every subsequent migration run.

## Open questions

- Who owns verifying that no production Postgres instance has
  `run_task_state_events` rows that have NOT been reconciled into
  `run_graph_mutations`? A pre-migration audit script is probably worth 30
  minutes (see §Testing approach — pre-migration audit).
- Naming for the archive file — `exports/` directory (as proposed) or a
  dedicated `archives/` directory?
- Should the sentinel test `test_legacy_wal_absent.py` live in `tests/state/`
  (alongside other state tests) or in a dedicated `tests/schema/` directory
  to group all schema-invariant tests together?

## On acceptance

- [ ] Update `docs/architecture/02_runtime_lifecycle.md#invariants` — remove
  the `RunTaskStateEvent` deprecation note from §4.1 Known limits and the RFC
  link from §7.
- [ ] Update `docs/architecture/04_persistence.md#core-abstractions` — remove
  the frozen-table invariant from §4 and the anti-pattern bullet from §6; update
  §2 and §7 as described in §Invariants affected.
- [ ] Link the implementation plan at
  `docs/superpowers/plans/2026-04-??-delete-run-task-state-event.md` (if
  created separately; otherwise this RFC serves as the plan).
- [ ] Move this file to `docs/rfcs/accepted/`.
