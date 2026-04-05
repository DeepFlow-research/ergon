"""Workflow finalization invariant tests.

Tests score aggregation edge cases where None-scored evaluations
could silently deflate averages if treated as 0.
"""

from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from sqlmodel import Session

from h_arcane.core.persistence.shared.enums import RunStatus
from h_arcane.core.persistence.telemetry.models import RunRecord, RunTaskEvaluation
from h_arcane.core.runtime.services.orchestration_dto import FinalizeWorkflowCommand
from h_arcane.core.runtime.services.workflow_finalization_service import (
    WorkflowFinalizationService,
)
from tests.state.factories import seed_flat_tasks


def _fake_get_session(real_session: Session):
    """Return a context-manager-compatible stand-in that delegates to the
    test session without closing it or committing the outer transaction."""
    ctx = MagicMock()
    ctx.__enter__ = MagicMock(return_value=real_session)
    ctx.__exit__ = MagicMock(return_value=False)
    return ctx


class TestScoreAggregation:

    def test_finalize_score_aggregation_with_mixed_nones(self, session: Session):
        def_id, _, task_ids = seed_flat_tasks(session, 3)
        run_id = uuid4()

        session.add(RunRecord(
            id=run_id,
            experiment_definition_id=def_id,
            status=RunStatus.EXECUTING,
        ))

        scores: list[float | None] = [0.8, None, 0.6]
        for tid, score in zip(task_ids, scores):
            session.add(RunTaskEvaluation(
                run_id=run_id,
                definition_task_id=tid,
                definition_evaluator_id=uuid4(),
                score=score,
                summary_json={},
            ))

        session.flush()

        svc = WorkflowFinalizationService()

        with patch(
            "h_arcane.core.runtime.services.workflow_finalization_service.get_session",
            return_value=_fake_get_session(session),
        ):
            result = svc.finalize(FinalizeWorkflowCommand(
                run_id=run_id, definition_id=def_id,
            ))

        assert result.final_score == pytest.approx(1.4)
        assert result.normalized_score == pytest.approx(0.7)
        assert result.evaluators_count == 3
