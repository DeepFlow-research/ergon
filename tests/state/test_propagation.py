"""DAG propagation invariant tests.

Tests the functions in propagation.py directly (they take Session),
bypassing the thin service wrappers.
"""

from uuid import uuid4

from sqlmodel import Session

from h_arcane.core.persistence.shared.enums import TaskExecutionStatus
from h_arcane.core.runtime.execution.propagation import (
    get_initial_ready_tasks,
    is_workflow_complete,
    is_workflow_failed,
    mark_task_completed,
    mark_task_failed,
    on_task_completed,
)
from tests.state.factories import (
    seed_chain,
    seed_diamond,
    seed_flat_tasks,
    seed_run,
)


class TestDiamondFanIn:

    def test_diamond_fan_in_waits_for_all_deps(self, session: Session):
        """D should only become ready when BOTH B and C are completed."""
        def_id, _, task_ids, _ = seed_diamond(session)
        a, b, c, d = task_ids
        run_id = seed_run(session, def_id)

        ready = get_initial_ready_tasks(session, run_id, def_id)
        assert set(ready) == {a}

        after_a = on_task_completed(session, run_id, def_id, a, uuid4())
        assert set(after_a) == {b, c}

        after_b = on_task_completed(session, run_id, def_id, b, uuid4())
        assert d not in after_b

        after_c = on_task_completed(session, run_id, def_id, c, uuid4())
        assert d in after_c


class TestChainPropagation:

    def test_chain_propagation_step_by_step(self, session: Session):
        def_id, _, task_ids, _ = seed_chain(session, 3)
        a, b, c = task_ids
        run_id = seed_run(session, def_id)

        ready = get_initial_ready_tasks(session, run_id, def_id)
        assert set(ready) == {a}

        after_a = on_task_completed(session, run_id, def_id, a, uuid4())
        assert set(after_a) == {b}

        after_b = on_task_completed(session, run_id, def_id, b, uuid4())
        assert set(after_b) == {c}

        after_c = on_task_completed(session, run_id, def_id, c, uuid4())
        assert after_c == []

        assert is_workflow_complete(session, run_id, def_id)


class TestFlatTasks:

    def test_flat_tasks_all_initially_ready(self, session: Session):
        def_id, _, task_ids = seed_flat_tasks(session, 3)
        run_id = seed_run(session, def_id)

        ready = get_initial_ready_tasks(session, run_id, def_id)
        assert set(ready) == set(task_ids)


class TestFailureDetection:

    def test_is_workflow_failed_when_any_task_fails(self, session: Session):
        def_id, _, task_ids = seed_flat_tasks(session, 3)
        run_id = seed_run(session, def_id)

        mark_task_completed(session, run_id, task_ids[0], uuid4())
        mark_task_failed(session, run_id, task_ids[1], "boom")
        session.flush()

        assert is_workflow_failed(session, run_id, def_id)
        assert not is_workflow_complete(session, run_id, def_id)


class TestCompletionRequiresAll:

    def test_is_workflow_complete_requires_all_tasks(self, session: Session):
        def_id, _, task_ids = seed_flat_tasks(session, 3)
        run_id = seed_run(session, def_id)

        mark_task_completed(session, run_id, task_ids[0], uuid4())
        mark_task_completed(session, run_id, task_ids[1], uuid4())
        session.flush()

        assert not is_workflow_complete(session, run_id, def_id)
