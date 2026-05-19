"""Compatibility helpers for retired experiment-definition records.

Deletion owner: PR 09 removes this module after dashboard/CLI/test fallback
paths no longer need the retired ``experiments`` table.
"""

from uuid import UUID

from ergon_core.core.persistence.telemetry.models import BenchmarkDefinitionRecord
from ergon_core.core.views.experiments.models import (
    ExperimentDetailDto,
    ExperimentSummaryDto,
)
from sqlmodel import Session


def dict_metadata(metadata: dict, key: str) -> dict:
    value = metadata.get(key)
    return dict(value) if isinstance(value, dict) else {}


def optional_str_metadata(metadata: dict, key: str) -> str | None:
    value = metadata.get(key)
    return value if isinstance(value, str) else None


def legacy_experiment_detail(
    session: Session,
    definition_id: UUID,
) -> ExperimentDetailDto | None:
    """Build a display DTO from a deprecated ``BenchmarkDefinitionRecord``."""
    record = session.get(BenchmarkDefinitionRecord, definition_id)
    if record is None:
        return None

    summary = _legacy_summary(record)
    return ExperimentDetailDto(
        definition_id=record.id,
        name=record.name,
        description=None,
        benchmark_type=record.benchmark_type,
        experiment=summary,
        sample_selection=record.parsed_sample_selection(),
        design=record.parsed_design(),
        metadata=record.parsed_metadata(),
    )


def _legacy_summary(record: BenchmarkDefinitionRecord) -> ExperimentSummaryDto:
    return ExperimentSummaryDto(
        definition_id=record.id,
        cohort_id=record.cohort_id,
        name=record.name,
        description=None,
        benchmark_type=record.benchmark_type,
        sample_count=record.sample_count,
        status=record.status,
        default_worker_team=record.parsed_default_worker_team(),
        default_evaluator_slug=record.default_evaluator_slug,
        default_model_target=record.default_model_target,
        created_by=None,
        created_at=record.created_at,
        started_at=record.started_at,
        completed_at=record.completed_at,
        run_count=0,
    )
