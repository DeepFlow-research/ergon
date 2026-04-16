"""Unit tests for restart_task (Phase 1) and downstream invalidation (Phase 2).

Phase 1 tests cover the simple reset: terminal -> pending, outgoing edges
reset to EDGE_PENDING, task/ready emitted, and rejection of non-terminal
status. Phase 2 will add downstream invalidation assertions in this same
file once the cascade is implemented.
"""

from unittest.mock import patch
from uuid import uuid4

import pytest
from ergon_core.core.persistence.graph.status_conventions import (
    CANCELLED,
    COMPLETED,
    EDGE_INVALIDATED,
    EDGE_PENDING,
    EDGE_SATISFIED,
    FAILED,
    PENDING,
    RUNNING,
)
from ergon_core.core.runtime.errors.delegation_errors import TaskNotTerminalError
from ergon_core.core.runtime.services.graph_dto import MutationMeta
from ergon_core.core.runtime.services.graph_repository import WorkflowGraphRepository
from ergon_core.core.runtime.services.task_management_dto import RestartTaskCommand
from ergon_core.core.runtime.services.task_management_service import (
    TaskManagementService,
)
from sqlmodel import Session

from tests.state.mocks import FakeInngestClient

META = MutationMeta(actor="test", reason="test-setup")


def _add_node(
    repo: WorkflowGraphRepository,
    session: Session,
    run_id,
    key: str,
    *,
    status: str = PENDING,
    instance_key: str = "inst-0",
    parent_node_id=None,
    level: int = 0,
):
    return repo.add_node(
        session,
        run_id,
        task_key=key,
        instance_key=instance_key,
        description=f"node {key}",
        status=status,
        parent_node_id=parent_node_id,
        level=level,
        meta=META,
    )


class TestRestartTaskBasic:
    """Phase 1: terminal -> PENDING with edge reset and task/ready dispatch."""

    @pytest.mark.parametrize("terminal_status", [COMPLETED, FAILED, CANCELLED])
    def test_restarts_from_terminal(self, session: Session, terminal_status: str):
        """restart_task resets a terminal node to PENDING."""
        fake = FakeInngestClient()
        repo = WorkflowGraphRepository()
        svc = TaskManagementService(graph_repo=repo)
        run_id = uuid4()

        node = _add_node(repo, session, run_id, "target", status=terminal_status)

        with patch(
            "ergon_core.core.runtime.services.task_management_service.inngest_client",
            fake,
        ):
            result = svc.restart_task(
                session,
                RestartTaskCommand(run_id=run_id, node_id=node.id),
            )

        assert result.old_status == terminal_status
        updated = repo.get_node(session, run_id=run_id, node_id=node.id)
        assert updated.status == PENDING

    def test_emits_task_ready(self, session: Session):
        """restart_task emits a task/ready Inngest event so the scheduler picks up the node."""
        fake = FakeInngestClient()
        repo = WorkflowGraphRepository()
        svc = TaskManagementService(graph_repo=repo)
        run_id = uuid4()

        node = _add_node(repo, session, run_id, "target", status=COMPLETED)

        with patch(
            "ergon_core.core.runtime.services.task_management_service.inngest_client",
            fake,
        ):
            svc.restart_task(
                session,
                RestartTaskCommand(run_id=run_id, node_id=node.id),
            )

        ready_events = fake.events_by_name("task/ready")
        assert len(ready_events) == 1
        assert ready_events[0].data["node_id"] == str(node.id)

    def test_resets_outgoing_edges(self, session: Session):
        """Outgoing SATISFIED / INVALIDATED edges are reset to EDGE_PENDING on restart."""
        fake = FakeInngestClient()
        repo = WorkflowGraphRepository()
        svc = TaskManagementService(graph_repo=repo)
        run_id = uuid4()

        # Parent + two downstream nodes. Source node has two outgoing edges
        # in different states to prove both kinds get reset.
        parent = _add_node(repo, session, run_id, "manager", status=RUNNING)
        source = _add_node(
            repo, session, run_id, "src", status=COMPLETED, parent_node_id=parent.id, level=1
        )
        t_pending = _add_node(
            repo,
            session,
            run_id,
            "t-pending",
            status=PENDING,
            parent_node_id=parent.id,
            level=1,
        )
        t_cancelled = _add_node(
            repo,
            session,
            run_id,
            "t-cancelled",
            status=CANCELLED,
            parent_node_id=parent.id,
            level=1,
        )

        repo.add_edge(
            session,
            run_id,
            source_node_id=source.id,
            target_node_id=t_pending.id,
            status=EDGE_SATISFIED,
            meta=META,
        )
        repo.add_edge(
            session,
            run_id,
            source_node_id=source.id,
            target_node_id=t_cancelled.id,
            status=EDGE_INVALIDATED,
            meta=META,
        )
        session.commit()

        with patch(
            "ergon_core.core.runtime.services.task_management_service.inngest_client",
            fake,
        ):
            svc.restart_task(
                session,
                RestartTaskCommand(run_id=run_id, node_id=source.id),
            )

        outgoing = repo.get_outgoing_edges(session, run_id=run_id, node_id=source.id)
        assert len(outgoing) == 2
        assert all(e.status == EDGE_PENDING for e in outgoing)

    def test_status_change_mutation_logged(self, session: Session):
        """restart_task writes a node.status_changed mutation (terminal -> pending)."""
        fake = FakeInngestClient()
        repo = WorkflowGraphRepository()
        svc = TaskManagementService(graph_repo=repo)
        run_id = uuid4()

        node = _add_node(repo, session, run_id, "target", status=COMPLETED)
        seq_before = len(repo.get_mutations(session, run_id))

        with patch(
            "ergon_core.core.runtime.services.task_management_service.inngest_client",
            fake,
        ):
            svc.restart_task(
                session,
                RestartTaskCommand(run_id=run_id, node_id=node.id),
            )

        new_mutations = repo.get_mutations(session, run_id)[seq_before:]
        status_changes = [m for m in new_mutations if m.mutation_type == "node.status_changed"]
        assert len(status_changes) == 1
        assert status_changes[0].old_value.status == COMPLETED  # type: ignore[union-attr]
        assert status_changes[0].new_value.status == PENDING  # type: ignore[union-attr]

    @pytest.mark.parametrize("live_status", [PENDING, RUNNING])
    def test_rejects_non_terminal(self, session: Session, live_status: str):
        """restart_task rejects PENDING and RUNNING nodes."""
        repo = WorkflowGraphRepository()
        svc = TaskManagementService(graph_repo=repo)
        run_id = uuid4()

        node = _add_node(repo, session, run_id, "target", status=live_status)

        with pytest.raises(TaskNotTerminalError) as exc_info:
            svc.restart_task(
                session,
                RestartTaskCommand(run_id=run_id, node_id=node.id),
            )
        assert exc_info.value.node_id == node.id
        assert exc_info.value.current_status == live_status

    def test_no_outgoing_edges_still_works(self, session: Session):
        """A leaf node (no outgoing edges) restarts cleanly."""
        fake = FakeInngestClient()
        repo = WorkflowGraphRepository()
        svc = TaskManagementService(graph_repo=repo)
        run_id = uuid4()

        node = _add_node(repo, session, run_id, "leaf", status=FAILED)

        with patch(
            "ergon_core.core.runtime.services.task_management_service.inngest_client",
            fake,
        ):
            result = svc.restart_task(
                session,
                RestartTaskCommand(run_id=run_id, node_id=node.id),
            )

        assert result.old_status == FAILED
        assert result.invalidated_node_ids == []
        updated = repo.get_node(session, run_id=run_id, node_id=node.id)
        assert updated.status == PENDING


def _build_chain(repo, session, run_id, parent_id, keys: list[str], statuses: list[str]):
    """Helper: build a straight A→B→C chain with specified statuses."""
    assert len(keys) == len(statuses)
    nodes = []
    for key, status in zip(keys, statuses, strict=True):
        nodes.append(
            _add_node(
                repo,
                session,
                run_id,
                key,
                status=status,
                parent_node_id=parent_id,
                level=1,
            )
        )
    for src, tgt, tgt_status in zip(nodes[:-1], nodes[1:], statuses[1:], strict=True):
        # A completed source with a completed downstream uses SATISFIED
        # edges; every other combination uses PENDING. We infer based on
        # whether the source is COMPLETED.
        edge_status = (
            EDGE_SATISFIED if src.status == COMPLETED and tgt_status != PENDING else EDGE_PENDING
        )
        repo.add_edge(
            session,
            run_id,
            source_node_id=src.id,
            target_node_id=tgt.id,
            status=edge_status,
            meta=META,
        )
    session.commit()
    return nodes


class TestDownstreamInvalidation:
    """Phase 2: invalidate downstream targets when an upstream node is restarted."""

    def test_running_target_cancelled(self, session: Session):
        """Restart D while E is RUNNING → E is CANCELLED, D→E edge reset."""
        fake = FakeInngestClient()
        repo = WorkflowGraphRepository()
        svc = TaskManagementService(graph_repo=repo)
        run_id = uuid4()

        parent = _add_node(repo, session, run_id, "manager", status=RUNNING)
        d, e = _build_chain(repo, session, run_id, parent.id, ["D", "E"], [COMPLETED, RUNNING])

        with patch(
            "ergon_core.core.runtime.services.task_management_service.inngest_client",
            fake,
        ):
            result = svc.restart_task(
                session,
                RestartTaskCommand(run_id=run_id, node_id=d.id),
            )

        assert e.id in result.invalidated_node_ids
        e_after = repo.get_node(session, run_id=run_id, node_id=e.id)
        assert e_after.status == CANCELLED

        # D→E edge was reset by restart_task's own loop.
        outgoing = repo.get_outgoing_edges(session, run_id=run_id, node_id=d.id)
        assert all(edge.status == EDGE_PENDING for edge in outgoing)

        # task/cancelled emitted for E.
        cancelled_events = fake.events_by_name("task/cancelled")
        assert any(evt.data["node_id"] == str(e.id) for evt in cancelled_events)
        assert any(evt.data["cause"] == "downstream_invalidation" for evt in cancelled_events)

    def test_completed_target_cancelled_and_edges_reset(self, session: Session):
        """Restart D while E is COMPLETED → E cancelled, E's outgoing edges reset."""
        fake = FakeInngestClient()
        repo = WorkflowGraphRepository()
        svc = TaskManagementService(graph_repo=repo)
        run_id = uuid4()

        parent = _add_node(repo, session, run_id, "manager", status=RUNNING)
        d, e, g = _build_chain(
            repo,
            session,
            run_id,
            parent.id,
            ["D", "E", "G"],
            [COMPLETED, COMPLETED, PENDING],
        )
        # E→G was created EDGE_PENDING by helper (G status was PENDING), so
        # set it to SATISFIED manually to represent the "E completed then G
        # was cancelled separately" vs. "E completed but G blocked" — here
        # we just want to prove E's outgoing edge resets regardless.
        e_out = repo.get_outgoing_edges(session, run_id=run_id, node_id=e.id)
        if e_out and e_out[0].status != EDGE_SATISFIED:
            repo.update_edge_status(
                session,
                run_id=run_id,
                edge_id=e_out[0].id,
                new_status=EDGE_SATISFIED,
                meta=META,
            )
            session.commit()

        with patch(
            "ergon_core.core.runtime.services.task_management_service.inngest_client",
            fake,
        ):
            result = svc.restart_task(
                session,
                RestartTaskCommand(run_id=run_id, node_id=d.id),
            )

        assert e.id in result.invalidated_node_ids
        e_after = repo.get_node(session, run_id=run_id, node_id=e.id)
        assert e_after.status == CANCELLED

        # E's outgoing edge (E→G) was reset because E was COMPLETED and had
        # to have its output invalidated deeper.
        e_out_after = repo.get_outgoing_edges(session, run_id=run_id, node_id=e.id)
        assert all(edge.status == EDGE_PENDING for edge in e_out_after)
        # G was PENDING, so it also gets cancelled by the cascade.
        g_after = repo.get_node(session, run_id=run_id, node_id=g.id)
        assert g_after.status == CANCELLED

    def test_deep_chain_cascades(self, session: Session):
        """Deep chain D→E→G, all COMPLETED. Restart D → E and G both invalidated."""
        fake = FakeInngestClient()
        repo = WorkflowGraphRepository()
        svc = TaskManagementService(graph_repo=repo)
        run_id = uuid4()

        parent = _add_node(repo, session, run_id, "manager", status=RUNNING)
        d, e, g = _build_chain(
            repo,
            session,
            run_id,
            parent.id,
            ["D", "E", "G"],
            [COMPLETED, COMPLETED, COMPLETED],
        )
        # Helper wires PENDING edges when target is COMPLETED; fix for
        # the steady-state pre-restart case where all edges are SATISFIED.
        for src_node in (d, e):
            for edge in repo.get_outgoing_edges(session, run_id=run_id, node_id=src_node.id):
                if edge.status != EDGE_SATISFIED:
                    repo.update_edge_status(
                        session,
                        run_id=run_id,
                        edge_id=edge.id,
                        new_status=EDGE_SATISFIED,
                        meta=META,
                    )
        session.commit()

        with patch(
            "ergon_core.core.runtime.services.task_management_service.inngest_client",
            fake,
        ):
            result = svc.restart_task(
                session,
                RestartTaskCommand(run_id=run_id, node_id=d.id),
            )

        assert set(result.invalidated_node_ids) == {e.id, g.id}
        e_after = repo.get_node(session, run_id=run_id, node_id=e.id)
        g_after = repo.get_node(session, run_id=run_id, node_id=g.id)
        assert e_after.status == CANCELLED
        assert g_after.status == CANCELLED

        # All edges in the chain are reset.
        for src_node in (d, e):
            for edge in repo.get_outgoing_edges(session, run_id=run_id, node_id=src_node.id):
                assert edge.status == EDGE_PENDING

    def test_fan_in_invalidation_resets_both_incoming_edges(self, session: Session):
        """Restart B (A→B→F, A→C→F, F COMPLETED). F cancelled + both B→F and C→F reset."""
        fake = FakeInngestClient()
        repo = WorkflowGraphRepository()
        svc = TaskManagementService(graph_repo=repo)
        run_id = uuid4()

        parent = _add_node(repo, session, run_id, "manager", status=RUNNING)

        # Build diamond: A→B, A→C, B→F, C→F. All COMPLETED.
        a = _add_node(
            repo, session, run_id, "A", status=COMPLETED, parent_node_id=parent.id, level=1
        )
        b = _add_node(
            repo, session, run_id, "B", status=COMPLETED, parent_node_id=parent.id, level=1
        )
        c = _add_node(
            repo, session, run_id, "C", status=COMPLETED, parent_node_id=parent.id, level=1
        )
        f = _add_node(
            repo, session, run_id, "F", status=COMPLETED, parent_node_id=parent.id, level=1
        )
        for src, tgt in [(a, b), (a, c), (b, f), (c, f)]:
            repo.add_edge(
                session,
                run_id,
                source_node_id=src.id,
                target_node_id=tgt.id,
                status=EDGE_SATISFIED,
                meta=META,
            )
        session.commit()

        with patch(
            "ergon_core.core.runtime.services.task_management_service.inngest_client",
            fake,
        ):
            result = svc.restart_task(
                session,
                RestartTaskCommand(run_id=run_id, node_id=b.id),
            )

        assert f.id in result.invalidated_node_ids
        f_after = repo.get_node(session, run_id=run_id, node_id=f.id)
        assert f_after.status == CANCELLED

        # Both incoming edges to F (B→F and C→F) must be EDGE_PENDING.
        # B→F reset by restart_task's own loop; C→F reset by the cascade
        # when it recursed into F (via _reset_outgoing_edges on F — but
        # F has no outgoing here; the important semantic is the INCOMING
        # to F). Wait: the plan says C→F must be reset too. That has to
        # happen explicitly.
        incoming_to_f = repo.get_incoming_edges(session, run_id=run_id, node_id=f.id)
        statuses = {edge.source_node_id: edge.status for edge in incoming_to_f}
        # B→F: reset because B's outgoing was reset on restart.
        assert statuses[b.id] == EDGE_PENDING
        # C→F: must be reset when F is cancelled as part of invalidation,
        # otherwise F can never re-activate (C→F is still SATISFIED from
        # the old C completion).
        assert statuses[c.id] == EDGE_PENDING

    def test_already_cancelled_downstream_left_alone(self, session: Session):
        """Downstream target that is already CANCELLED is not re-cancelled."""
        fake = FakeInngestClient()
        repo = WorkflowGraphRepository()
        svc = TaskManagementService(graph_repo=repo)
        run_id = uuid4()

        parent = _add_node(repo, session, run_id, "manager", status=RUNNING)
        d, e = _build_chain(repo, session, run_id, parent.id, ["D", "E"], [COMPLETED, CANCELLED])

        with patch(
            "ergon_core.core.runtime.services.task_management_service.inngest_client",
            fake,
        ):
            result = svc.restart_task(
                session,
                RestartTaskCommand(run_id=run_id, node_id=d.id),
            )

        # E was already CANCELLED; the invalidation cascade should skip it.
        assert e.id not in result.invalidated_node_ids
        e_after = repo.get_node(session, run_id=run_id, node_id=e.id)
        assert e_after.status == CANCELLED

    def test_failed_downstream_left_alone(self, session: Session):
        """Downstream target that is FAILED is not touched."""
        fake = FakeInngestClient()
        repo = WorkflowGraphRepository()
        svc = TaskManagementService(graph_repo=repo)
        run_id = uuid4()

        parent = _add_node(repo, session, run_id, "manager", status=RUNNING)
        d, e = _build_chain(repo, session, run_id, parent.id, ["D", "E"], [COMPLETED, FAILED])

        with patch(
            "ergon_core.core.runtime.services.task_management_service.inngest_client",
            fake,
        ):
            result = svc.restart_task(
                session,
                RestartTaskCommand(run_id=run_id, node_id=d.id),
            )

        assert e.id not in result.invalidated_node_ids
        e_after = repo.get_node(session, run_id=run_id, node_id=e.id)
        assert e_after.status == FAILED
