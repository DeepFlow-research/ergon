"""Dashboard event projections for persisted graph mutation rows."""

from typing import cast

from ergon_core.core.application.graph.models import (
    GraphMutationRecordDto,
    GraphMutationValue,
)
from ergon_core.core.persistence.graph.models import (
    GraphTargetType,
    MutationType,
    RunGraphMutation,
)
from ergon_core.core.persistence.shared.types import RunId
from ergon_core.core.views.dashboard_events.contracts import DashboardGraphMutationEvent


def graph_mutation_record_from_row(row: RunGraphMutation) -> GraphMutationRecordDto:
    return GraphMutationRecordDto(
        id=row.id,
        run_id=cast(RunId, row.run_id),
        sequence=row.sequence,
        mutation_type=cast(MutationType, row.mutation_type),
        target_type=cast(GraphTargetType, row.target_type),
        target_id=row.target_id,
        actor=row.actor,
        old_value=cast(GraphMutationValue | None, dict(row.old_value)) if row.old_value else None,
        new_value=cast(GraphMutationValue, dict(row.new_value)),
        reason=row.reason,
        created_at=row.created_at,
    )


def dashboard_graph_mutation_event_from_row(
    row: RunGraphMutation,
) -> DashboardGraphMutationEvent:
    return DashboardGraphMutationEvent(mutation=graph_mutation_record_from_row(row))
