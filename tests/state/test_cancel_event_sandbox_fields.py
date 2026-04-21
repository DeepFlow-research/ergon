"""Tests for sandbox_id + benchmark_slug population on TaskCancelledEvent.

Verifies:
- _lookup_sandbox_id returns the correct value from RunTaskExecution
- _lookup_benchmark_slug returns the correct benchmark type from the run's definition
- SubtaskCancellationService.cancel_orphans populates sandbox_id on emitted events
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from sqlmodel import Session

from ergon_core.core.persistence.definitions.models import ExperimentDefinition
from ergon_core.core.persistence.graph.status_conventions import PENDING, RUNNING
from ergon_core.core.persistence.shared.enums import RunStatus, TaskExecutionStatus
from ergon_core.core.persistence.telemetry.models import RunRecord, RunTaskExecution
from ergon_core.core.runtime.services._cancel_helpers import (
    _lookup_benchmark_slug,
    _lookup_sandbox_id,
)


def _seed_definition(session: Session, *, benchmark_type: str = "swebench-verified") -> uuid4:
    """Seed a minimal ExperimentDefinition row."""
    def_id = uuid4()
    session.add(ExperimentDefinition(id=def_id, benchmark_type=benchmark_type))
    session.flush()
    return def_id


def _seed_run(session: Session, definition_id) -> uuid4:
    """Seed a RunRecord referencing the given definition."""
    run_id = uuid4()
    session.add(
        RunRecord(id=run_id, experiment_definition_id=definition_id, status=RunStatus.PENDING)
    )
    session.flush()
    return run_id


def _seed_execution(
    session: Session,
    *,
    run_id,
    node_id,
    sandbox_id: str | None = "sbx-abc123",
    status=TaskExecutionStatus.RUNNING,
) -> RunTaskExecution:
    exe = RunTaskExecution(
        run_id=run_id,
        node_id=node_id,
        status=status,
        sandbox_id=sandbox_id,
    )
    session.add(exe)
    session.flush()
    return exe


class TestLookupSandboxId:
    def test_returns_sandbox_id_for_known_execution(self, session: Session) -> None:
        run_id = uuid4()
        node_id = uuid4()
        exe = _seed_execution(session, run_id=run_id, node_id=node_id, sandbox_id="sbx-xyz")

        result = _lookup_sandbox_id(session, exe.id)

        assert result == "sbx-xyz"

    def test_returns_none_for_none_execution_id(self, session: Session) -> None:
        result = _lookup_sandbox_id(session, None)
        assert result is None

    def test_returns_none_for_missing_execution(self, session: Session) -> None:
        result = _lookup_sandbox_id(session, uuid4())
        assert result is None

    def test_returns_none_for_null_sandbox_id_column(self, session: Session) -> None:
        run_id = uuid4()
        node_id = uuid4()
        exe = _seed_execution(session, run_id=run_id, node_id=node_id, sandbox_id=None)

        result = _lookup_sandbox_id(session, exe.id)

        assert result is None


class TestLookupBenchmarkSlug:
    def test_returns_benchmark_type_for_known_run(self, session: Session) -> None:
        def_id = _seed_definition(session, benchmark_type="swebench-verified")
        run_id = _seed_run(session, def_id)

        result = _lookup_benchmark_slug(session, run_id)

        assert result == "swebench-verified"

    def test_returns_none_for_missing_run(self, session: Session) -> None:
        result = _lookup_benchmark_slug(session, uuid4())
        assert result is None

    def test_returns_correct_slug_for_minif2f(self, session: Session) -> None:
        def_id = _seed_definition(session, benchmark_type="minif2f")
        run_id = _seed_run(session, def_id)

        result = _lookup_benchmark_slug(session, run_id)

        assert result == "minif2f"


class TestSubtaskCancellationServiceSandboxFields:
    """Verify SubtaskCancellationService.cancel_orphans populates sandbox_id."""

    def test_cancel_orphans_populates_sandbox_id(self, session: Session) -> None:
        """cancel_orphans should include sandbox_id on transitioned nodes."""
        from ergon_core.core.persistence.graph.models import RunGraphNode
        from ergon_core.core.runtime.services.graph_dto import MutationMeta
        from ergon_core.core.runtime.services.graph_repository import WorkflowGraphRepository
        from ergon_core.core.runtime.services.subtask_cancellation_service import (
            SubtaskCancellationService,
        )

        repo = WorkflowGraphRepository()
        svc = SubtaskCancellationService(graph_repo=repo)
        meta = MutationMeta(actor="test", reason="test-setup")

        def_id = _seed_definition(session, benchmark_type="swebench-verified")
        run_id = _seed_run(session, def_id)
        definition_id = uuid4()

        parent = repo.add_node(
            session,
            run_id,
            task_key="parent",
            instance_key="inst",
            description="parent node",
            status="cancelled",
            parent_node_id=None,
            level=0,
            meta=meta,
        )
        child = repo.add_node(
            session,
            run_id,
            task_key="child",
            instance_key="inst",
            description="child node",
            status=RUNNING,
            parent_node_id=parent.id,
            level=1,
            meta=meta,
        )
        session.flush()

        exe = _seed_execution(session, run_id=run_id, node_id=child.id, sandbox_id="sbx-child")
        session.flush()

        result = svc.cancel_orphans(
            session,
            run_id=run_id,
            definition_id=definition_id,
            parent_node_id=parent.id,
            cause="parent_terminal",
        )

        assert len(result.events_to_emit) == 1
        event = result.events_to_emit[0]
        assert event.sandbox_id == "sbx-child"
        assert event.execution_id == exe.id
        assert event.benchmark_slug == "swebench-verified"

    def test_cancel_orphans_sandbox_id_none_when_no_execution(self, session: Session) -> None:
        """cancel_orphans sets sandbox_id=None when node has no execution."""
        from ergon_core.core.runtime.services.graph_dto import MutationMeta
        from ergon_core.core.runtime.services.graph_repository import WorkflowGraphRepository
        from ergon_core.core.runtime.services.subtask_cancellation_service import (
            SubtaskCancellationService,
        )

        repo = WorkflowGraphRepository()
        svc = SubtaskCancellationService(graph_repo=repo)
        meta = MutationMeta(actor="test", reason="test-setup")

        def_id = _seed_definition(session, benchmark_type="minif2f")
        run_id = _seed_run(session, def_id)
        definition_id = uuid4()

        parent = repo.add_node(
            session,
            run_id,
            task_key="parent",
            instance_key="inst",
            description="parent",
            status="cancelled",
            parent_node_id=None,
            level=0,
            meta=meta,
        )
        child = repo.add_node(
            session,
            run_id,
            task_key="child",
            instance_key="inst",
            description="child",
            status=PENDING,
            parent_node_id=parent.id,
            level=1,
            meta=meta,
        )
        session.flush()
        # No execution seeded — task was never dispatched

        result = svc.cancel_orphans(
            session,
            run_id=run_id,
            definition_id=definition_id,
            parent_node_id=parent.id,
            cause="parent_terminal",
        )

        assert len(result.events_to_emit) == 1
        event = result.events_to_emit[0]
        assert event.sandbox_id is None
        assert event.execution_id is None
        assert event.benchmark_slug == "minif2f"
