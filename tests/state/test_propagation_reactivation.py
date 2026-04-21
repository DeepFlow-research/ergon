"""Phase 3: CANCELLED managed subtask re-activates when all deps re-satisfied.

When an upstream node is restarted via ``restart_task``, its downstream
targets are cancelled by the invalidation cascade.  When the upstream
completes again, propagation must detect that a CANCELLED managed subtask
now has all its deps COMPLETED and reset it to PENDING so the scheduler
can pick it up.

Static workflow nodes (``parent_node_id is None``) do NOT re-activate —
they have no supervisor to adapt and the static workflow expects terminal
nodes to stay terminal.
"""

from uuid import uuid4

from ergon_core.core.persistence.graph.status_conventions import (
    CANCELLED,
    COMPLETED,
    EDGE_PENDING,
    PENDING,
    RUNNING,
)
from ergon_core.core.runtime.execution.propagation import on_task_completed_or_failed
from ergon_core.core.runtime.services.graph_dto import MutationMeta
from ergon_core.core.runtime.services.graph_repository import WorkflowGraphRepository
from sqlmodel import Session

META = MutationMeta(actor="test", reason="test-setup")


async def _add_node(
    repo: WorkflowGraphRepository,
    session: Session,
    run_id,
    slug: str,
    *,
    status: str = PENDING,
    instance_key: str = "inst-0",
    parent_node_id=None,
    level: int = 0,
):
    return await repo.add_node(
        session,
        run_id,
        task_slug=slug,
        instance_key=instance_key,
        description=f"node {slug}",
        status=status,
        parent_node_id=parent_node_id,
        level=level,
        meta=META,
    )


class TestReactivationOnDepCompletion:
    """CANCELLED managed subtask -> PENDING when all deps are COMPLETED."""

    async def test_chain_reactivation(self, session: Session):
        """D completes, E (CANCELLED managed) re-activates to PENDING."""
        repo = WorkflowGraphRepository()
        run_id = uuid4()

        parent = await _add_node(repo, session, run_id, "manager", status=RUNNING)
        # D is about to transition to COMPLETED (precondition of
        # on_task_completed_or_failed: node is already terminal).
        d = await _add_node(
            repo, session, run_id, "D", status=COMPLETED, parent_node_id=parent.id, level=1
        )
        e = await _add_node(
            repo, session, run_id, "E", status=CANCELLED, parent_node_id=parent.id, level=1
        )
        await repo.add_edge(
            session,
            run_id,
            source_node_id=d.id,
            target_node_id=e.id,
            status=EDGE_PENDING,
            meta=META,
        )
        session.commit()

        newly_ready, invalidated = await on_task_completed_or_failed(
            session,
            run_id,
            d.id,
            COMPLETED,
            graph_repo=repo,
        )

        assert invalidated == []
        assert e.id in newly_ready
        e_after = repo.get_node(session, run_id=run_id, node_id=e.id)
        assert e_after.status == PENDING

    async def test_fan_in_reactivation(self, session: Session):
        """B completes, F (CANCELLED managed) re-activates because C is also COMPLETED."""
        repo = WorkflowGraphRepository()
        run_id = uuid4()

        parent = await _add_node(repo, session, run_id, "manager", status=RUNNING)
        b = await _add_node(
            repo, session, run_id, "B", status=COMPLETED, parent_node_id=parent.id, level=1
        )
        c = await _add_node(
            repo, session, run_id, "C", status=COMPLETED, parent_node_id=parent.id, level=1
        )
        f = await _add_node(
            repo, session, run_id, "F", status=CANCELLED, parent_node_id=parent.id, level=1
        )
        await repo.add_edge(
            session,
            run_id,
            source_node_id=b.id,
            target_node_id=f.id,
            status=EDGE_PENDING,
            meta=META,
        )
        await repo.add_edge(
            session,
            run_id,
            source_node_id=c.id,
            target_node_id=f.id,
            status=EDGE_PENDING,
            meta=META,
        )
        session.commit()

        newly_ready, _ = await on_task_completed_or_failed(
            session,
            run_id,
            b.id,
            COMPLETED,
            graph_repo=repo,
        )

        assert f.id in newly_ready
        f_after = repo.get_node(session, run_id=run_id, node_id=f.id)
        assert f_after.status == PENDING

    async def test_fan_in_waits_for_all_deps(self, session: Session):
        """B completes, F (CANCELLED) does NOT re-activate because C is still PENDING."""
        repo = WorkflowGraphRepository()
        run_id = uuid4()

        parent = await _add_node(repo, session, run_id, "manager", status=RUNNING)
        b = await _add_node(
            repo, session, run_id, "B", status=COMPLETED, parent_node_id=parent.id, level=1
        )
        c = await _add_node(
            repo, session, run_id, "C", status=PENDING, parent_node_id=parent.id, level=1
        )
        f = await _add_node(
            repo, session, run_id, "F", status=CANCELLED, parent_node_id=parent.id, level=1
        )
        for src in (b, c):
            await repo.add_edge(
                session,
                run_id,
                source_node_id=src.id,
                target_node_id=f.id,
                status=EDGE_PENDING,
                meta=META,
            )
        session.commit()

        newly_ready, _ = await on_task_completed_or_failed(
            session,
            run_id,
            b.id,
            COMPLETED,
            graph_repo=repo,
        )

        assert f.id not in newly_ready
        f_after = repo.get_node(session, run_id=run_id, node_id=f.id)
        assert f_after.status == CANCELLED

    async def test_static_cancelled_does_not_reactivate(self, session: Session):
        """CANCELLED node with parent_node_id=None (static workflow) stays CANCELLED."""
        repo = WorkflowGraphRepository()
        run_id = uuid4()

        # Both nodes are static workflow nodes: no parent_node_id.
        d = await _add_node(repo, session, run_id, "D_static", status=COMPLETED)
        e = await _add_node(repo, session, run_id, "E_static", status=CANCELLED)
        await repo.add_edge(
            session,
            run_id,
            source_node_id=d.id,
            target_node_id=e.id,
            status=EDGE_PENDING,
            meta=META,
        )
        session.commit()

        newly_ready, _ = await on_task_completed_or_failed(
            session,
            run_id,
            d.id,
            COMPLETED,
            graph_repo=repo,
        )

        assert e.id not in newly_ready
        e_after = repo.get_node(session, run_id=run_id, node_id=e.id)
        assert e_after.status == CANCELLED

    async def test_pending_still_activates_normally(self, session: Session):
        """Normal first-activation path unchanged: PENDING target -> PENDING (ready)."""
        repo = WorkflowGraphRepository()
        run_id = uuid4()

        parent = await _add_node(repo, session, run_id, "manager", status=RUNNING)
        d = await _add_node(
            repo, session, run_id, "D", status=COMPLETED, parent_node_id=parent.id, level=1
        )
        e = await _add_node(
            repo, session, run_id, "E", status=PENDING, parent_node_id=parent.id, level=1
        )
        await repo.add_edge(
            session,
            run_id,
            source_node_id=d.id,
            target_node_id=e.id,
            status=EDGE_PENDING,
            meta=META,
        )
        session.commit()

        newly_ready, _ = await on_task_completed_or_failed(
            session,
            run_id,
            d.id,
            COMPLETED,
            graph_repo=repo,
        )

        assert e.id in newly_ready

    async def test_completed_target_not_reactivated(self, session: Session):
        """A COMPLETED target is NOT re-activated (it already ran, output is current)."""
        repo = WorkflowGraphRepository()
        run_id = uuid4()

        parent = await _add_node(repo, session, run_id, "manager", status=RUNNING)
        d = await _add_node(
            repo, session, run_id, "D", status=COMPLETED, parent_node_id=parent.id, level=1
        )
        e = await _add_node(
            repo, session, run_id, "E", status=COMPLETED, parent_node_id=parent.id, level=1
        )
        await repo.add_edge(
            session,
            run_id,
            source_node_id=d.id,
            target_node_id=e.id,
            status=EDGE_PENDING,
            meta=META,
        )
        session.commit()

        newly_ready, _ = await on_task_completed_or_failed(
            session,
            run_id,
            d.id,
            COMPLETED,
            graph_repo=repo,
        )

        assert e.id not in newly_ready
        e_after = repo.get_node(session, run_id=run_id, node_id=e.id)
        assert e_after.status == COMPLETED

    async def test_failed_target_not_reactivated(self, session: Session):
        """FAILED target stays FAILED — the manager must explicitly restart."""
        repo = WorkflowGraphRepository()
        run_id = uuid4()

        parent = await _add_node(repo, session, run_id, "manager", status=RUNNING)
        d = await _add_node(
            repo, session, run_id, "D", status=COMPLETED, parent_node_id=parent.id, level=1
        )
        e = await _add_node(
            repo, session, run_id, "E", status="failed", parent_node_id=parent.id, level=1
        )
        await repo.add_edge(
            session,
            run_id,
            source_node_id=d.id,
            target_node_id=e.id,
            status=EDGE_PENDING,
            meta=META,
        )
        session.commit()

        newly_ready, _ = await on_task_completed_or_failed(
            session,
            run_id,
            d.id,
            COMPLETED,
            graph_repo=repo,
        )

        assert e.id not in newly_ready
        e_after = repo.get_node(session, run_id=run_id, node_id=e.id)
        assert e_after.status == "failed"
