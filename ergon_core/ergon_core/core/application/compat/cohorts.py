"""Deprecated cohort compatibility service and marker helpers.

Deletion owner: PR 09 removes this module after cohort dashboard/routes and
test-harness dependencies are gone. Do not add new runtime behavior here.
"""

from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import UUID

from ergon_core.core.application.ports.dashboard import get_dashboard_event_publisher
from ergon_core.core.persistence.definitions.models import (
    ExperimentDefinition,
    ExperimentDefinitionInstance,
)
from ergon_core.core.shared.json_types import JsonObject
from ergon_core.core.persistence.shared.db import get_session
from ergon_core.core.persistence.shared.enums import RunStatus
from ergon_core.core.application.evaluation.summary import EvaluationSummary
from ergon_core.core.persistence.telemetry.models import (
    ExperimentCohort,
    ExperimentCohortStats,
    ExperimentCohortStatus,
    RunRecord,
)
from ergon_core.core.shared.utils import utcnow
from pydantic import BaseModel, Field
from sqlmodel import Session, select

COHORT_METADATA_KEY = "cohort_id"


def cohort_id_from_metadata(metadata: dict) -> UUID | None:
    """Read a deprecated cohort id marker from definition metadata."""
    raw = metadata.get(COHORT_METADATA_KEY)
    if raw is None:
        return None
    if isinstance(raw, UUID):
        return raw
    if isinstance(raw, str):
        return UUID(raw)
    return None


def cohort_id_for_trace_from_definition(definition: Any | None) -> str:
    """Return the deprecated cohort trace attribute for a definition, if present."""
    if definition is None:
        return ""
    raw = definition.parsed_metadata().get(COHORT_METADATA_KEY)
    return "" if raw is None else str(raw)


def optional_str_metadata(metadata: dict, key: str) -> str | None:
    value = metadata.get(key)
    return value if isinstance(value, str) else None


def build_legacy_cohort_marker_metadata(
    *,
    cohort_id: UUID,
    cohort_key: str,
    default_worker_team: dict | None = None,
    default_evaluator_slug: str | None = None,
    default_model_target: str | None = None,
    sandbox_slug: str | None = None,
    dependency_extras: list[str] | None = None,
    seeded: bool = False,
    status: str | None = None,
) -> dict[str, Any]:
    """Return temporary cohort metadata written for deprecated cohort views."""
    marker: dict[str, Any] = {
        COHORT_METADATA_KEY: str(cohort_id),
        "_test_cohort": cohort_key,
    }
    if seeded:
        marker["_test_seeded"] = True
    if default_worker_team is not None:
        marker["default_worker_team"] = default_worker_team
    if default_evaluator_slug is not None:
        marker["default_evaluator_slug"] = default_evaluator_slug
    if default_model_target is not None:
        marker["default_model_target"] = default_model_target
    if sandbox_slug is not None:
        marker["sandbox_slug"] = sandbox_slug
    if dependency_extras is not None:
        marker["dependency_extras"] = dependency_extras
    if status is not None:
        marker["status"] = status
    return marker


def write_legacy_cohort_marker(
    definition: Any,
    *,
    cohort_id: UUID,
    cohort_key: str,
    default_worker_team: dict | None = None,
    seeded: bool = False,
    status: str | None = None,
) -> None:
    """Mutate a deprecated definition row with temporary cohort metadata."""
    metadata = dict(definition.metadata_json)
    metadata.update(
        build_legacy_cohort_marker_metadata(
            cohort_id=cohort_id,
            cohort_key=cohort_key,
            default_worker_team=default_worker_team,
            seeded=seeded,
            status=status,
        )
    )
    definition.metadata_json = metadata


def remove_legacy_test_cohort_marker(definition: Any) -> None:
    """Remove test-only cohort marker keys from a deprecated definition row."""
    metadata = {} if definition.metadata_json is None else definition.metadata_json
    cleaned = dict(metadata)
    cleaned.pop(COHORT_METADATA_KEY, None)
    cleaned.pop("_test_seeded", None)
    cleaned.pop("_test_cohort", None)
    cleaned.pop("default_worker_team", None)
    cleaned.pop("status", None)
    definition.metadata_json = cleaned


def read_deprecated_cohort_id(cohort_key: str, session: Session) -> UUID | None:
    """Resolve a deprecated cohort name to its id for test/dashboard compatibility."""
    cohort = session.exec(
        select(ExperimentCohort).where(ExperimentCohort.name == cohort_key),
    ).first()
    return None if cohort is None else cohort.id


def deprecated_definition_ids_for_cohort(
    cohort_id: UUID,
    session: Session,
) -> list[UUID]:
    """Return definition ids carrying the deprecated cohort metadata marker."""
    return [
        definition.id
        for definition in session.exec(select(ExperimentDefinition)).all()
        if cohort_id_from_metadata(definition.parsed_metadata()) == cohort_id
    ]


class CohortStatusCountsDto(BaseModel):
    """Aggregate run counts by lifecycle status."""

    pending: int = 0
    executing: int = 0
    evaluating: int = 0
    completed: int = 0
    failed: int = 0


class CohortSummaryDto(BaseModel):
    """Summary row for cohort list and live updates."""

    cohort_id: UUID
    name: str
    description: str | None = None
    created_by: str | None = None
    created_at: datetime
    status: str
    total_runs: int = 0
    status_counts: CohortStatusCountsDto = Field(default_factory=CohortStatusCountsDto)
    average_score: float | None = None
    best_score: float | None = None
    worst_score: float | None = None
    average_duration_ms: int | None = None
    failure_rate: float = 0.0
    stats_updated_at: datetime | None = None


class CohortExperimentRowDto(BaseModel):
    """One experiment inside a cohort detail view."""

    definition_id: UUID
    name: str
    benchmark_type: str
    sample_count: int
    total_runs: int = 0
    status_counts: CohortStatusCountsDto = Field(default_factory=CohortStatusCountsDto)
    status: str
    created_at: datetime
    default_model_target: str | None = None
    default_evaluator_slug: str | None = None
    final_score: float | None = None
    total_cost_usd: float | None = None
    error_message: str | None = None


class CohortDetailDto(BaseModel):
    """Full payload for a single cohort detail page."""

    summary: CohortSummaryDto
    experiments: list[CohortExperimentRowDto] = Field(default_factory=list)


class UpdateCohortRequest(BaseModel):
    """Mutable cohort fields exposed through the operator API."""

    status: ExperimentCohortStatus


class ResolveCohortRequest(BaseModel):
    """Request to resolve or create a cohort by name."""

    name: str
    description: str | None = None
    created_by: str | None = None
    metadata: JsonObject = Field(default_factory=dict)


# TODO: this should not be a dataclass, it should be a Pydantic model
# TODO: now that experiments / cohorts have been thinned down, this mwhole file / repo needs a double check to see if it still earns its keep
@dataclass(frozen=True)
class RubricStatusSummary:
    status: str
    total_criteria: int
    passed: int = 0
    failed: int = 0
    errored: int = 0
    skipped: int = 0
    criterion_statuses: list[str] = field(default_factory=list)
    evaluator_names: list[str] = field(default_factory=list)


class DeprecatedCohortCompatibilityService:
    """Resolve deprecated cohorts and assemble temporary frontend DTOs."""

    def resolve_or_create(
        self,
        name: str,
        description: str | None = None,
        created_by: str | None = None,
    ) -> ExperimentCohort:
        """Resolve an existing cohort by name or create a new one."""
        with get_session() as session:
            stmt = select(ExperimentCohort).where(ExperimentCohort.name == name)
            existing = session.exec(stmt).first()
            if existing is not None:
                return existing

            cohort = ExperimentCohort(
                name=name,
                description=description,
                created_by=created_by,
            )
            session.add(cohort)
            session.commit()
            session.refresh(cohort)
            return cohort

    def list_summaries(self, *, include_archived: bool = False) -> list[CohortSummaryDto]:
        """List all cohorts as summary DTOs."""
        with get_session() as session:
            stmt = select(ExperimentCohort)
            if not include_archived:
                stmt = stmt.where(ExperimentCohort.status != ExperimentCohortStatus.ARCHIVED)
            cohorts = list(session.exec(stmt).all())

            results: list[CohortSummaryDto] = []
            for cohort in cohorts:
                stats = session.exec(
                    select(ExperimentCohortStats).where(
                        ExperimentCohortStats.cohort_id == cohort.id
                    )
                ).first()
                results.append(self._build_summary(cohort, stats))
            return results

    def get_detail(self, cohort_id: UUID) -> CohortDetailDto | None:
        """Get a cohort detail DTO with all experiments in the project folder."""
        with get_session() as session:
            cohort = session.get(ExperimentCohort, cohort_id)
            if cohort is None:
                return None

            stats = session.exec(
                select(ExperimentCohortStats).where(ExperimentCohortStats.cohort_id == cohort_id)
            ).first()
            summary = self._build_summary(cohort, stats)

            definitions = _definitions_for_cohort(session, cohort_id)
            experiment_rows = [
                self._build_experiment_row(
                    definition,
                    _instance_count(session, definition.id),
                    list(
                        session.exec(
                            select(RunRecord).where(
                                RunRecord.definition_id == definition.id
                            )
                        ).all()
                    ),
                )
                for definition in definitions
            ]
            return CohortDetailDto(summary=summary, experiments=experiment_rows)

    def get_summary(self, cohort_id: UUID) -> CohortSummaryDto | None:
        """Get a single cohort summary DTO."""
        with get_session() as session:
            cohort = session.get(ExperimentCohort, cohort_id)
            if cohort is None:
                return None
            stats = session.exec(
                select(ExperimentCohortStats).where(ExperimentCohortStats.cohort_id == cohort_id)
            ).first()
            return self._build_summary(cohort, stats)

    def cohort_id_for_run(self, run_id: UUID) -> UUID | None:
        """Return the owning cohort for a run, if one exists."""
        with get_session() as session:
            run = session.get(RunRecord, run_id)
            if run is None:
                return None
            definition = session.get(ExperimentDefinition, run.definition_id)
            if definition is None:
                return None
            return cohort_id_from_metadata(definition.parsed_metadata())

    def update_cohort(
        self, cohort_id: UUID, request: UpdateCohortRequest
    ) -> CohortSummaryDto | None:
        """Update mutable operator-facing cohort properties."""
        with get_session() as session:
            cohort = session.get(ExperimentCohort, cohort_id)
            if cohort is None:
                return None

            cohort.status = request.status.value
            cohort.updated_at = utcnow()
            session.add(cohort)
            session.commit()
            session.refresh(cohort)

            stats = session.exec(
                select(ExperimentCohortStats).where(ExperimentCohortStats.cohort_id == cohort_id)
            ).first()
            return self._build_summary(cohort, stats)

    def recompute(self, cohort_id: UUID) -> None:
        """Recompute and persist aggregate stats for one cohort."""
        with get_session() as session:
            definition_ids = [
                definition.id for definition in _definitions_for_cohort(session, cohort_id)
            ]
            runs = (
                list(
                    session.exec(
                        select(RunRecord).where(
                            RunRecord.definition_id.in_(definition_ids)  # type: ignore[attr-defined]
                        )
                    ).all()
                )
                if definition_ids
                else []
            )
            status_counts = Counter(run.status for run in runs)
            scored_values = [s for s in (_score_value(run) for run in runs) if s is not None]
            durations_ms = [
                int((run.completed_at - run.started_at).total_seconds() * 1000)
                for run in runs
                if run.started_at is not None and run.completed_at is not None
            ]
            total_runs = len(runs)
            failed_runs = status_counts.get(RunStatus.FAILED, 0)
            average_score = (sum(scored_values) / len(scored_values)) if scored_values else None
            average_duration_ms = (sum(durations_ms) // len(durations_ms)) if durations_ms else None

            stats = session.exec(
                select(ExperimentCohortStats).where(ExperimentCohortStats.cohort_id == cohort_id)
            ).first()
            if stats is None:
                stats = ExperimentCohortStats(cohort_id=cohort_id)

            stats.total_runs = total_runs
            stats.completed_runs = status_counts.get(RunStatus.COMPLETED, 0)
            stats.failed_runs = failed_runs
            stats.average_score = average_score
            stats.best_score = max(scored_values) if scored_values else None
            stats.worst_score = min(scored_values) if scored_values else None
            stats.average_duration_ms = average_duration_ms
            stats.failure_rate = (failed_runs / total_runs) if total_runs else 0.0
            stats.updated_at = utcnow()
            session.add(stats)
            session.commit()

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_summary(
        cohort: ExperimentCohort,
        stats: ExperimentCohortStats | None,
    ) -> CohortSummaryDto:
        return CohortSummaryDto(
            cohort_id=cohort.id,
            name=cohort.name,
            description=cohort.description,
            created_by=cohort.created_by,
            created_at=cohort.created_at,
            status=cohort.status,
            total_runs=stats.total_runs if stats else 0,
            status_counts=CohortStatusCountsDto(
                completed=stats.completed_runs if stats else 0,
                failed=stats.failed_runs if stats else 0,
            ),
            average_score=stats.average_score if stats else None,
            best_score=stats.best_score if stats else None,
            worst_score=stats.worst_score if stats else None,
            average_duration_ms=stats.average_duration_ms if stats else None,
            failure_rate=stats.failure_rate if stats else 0.0,
            stats_updated_at=stats.updated_at if stats else None,
        )

    @staticmethod
    def _build_experiment_row(
        definition: ExperimentDefinition,
        sample_count: int,
        runs: list[RunRecord],
    ) -> CohortExperimentRowDto:
        metadata = definition.parsed_metadata()
        score: float | None = None
        total_cost_usd: float | None = None
        for run in runs:
            summary = run.parsed_summary()
            raw_score = summary.get("normalized_score")
            if raw_score is None:
                raw_score = summary.get("final_score")
            if isinstance(raw_score, int | float):
                score = float(raw_score)
            raw_cost = summary.get("total_cost_usd")
            if isinstance(raw_cost, int | float):
                total_cost_usd = (total_cost_usd or 0.0) + float(raw_cost)

        status_counts = CohortStatusCountsDto()
        for run in runs:
            _increment_status_count(status_counts, str(run.status))

        return CohortExperimentRowDto(
            definition_id=definition.id,
            name=definition.name,
            benchmark_type=definition.benchmark_type,
            sample_count=sample_count,
            total_runs=len(runs),
            status_counts=status_counts,
            status=_experiment_row_status(
                str(metadata.get("status", "defined")),
                status_counts,
                len(runs),
            ),
            created_at=definition.created_at,
            default_model_target=optional_str_metadata(metadata, "default_model_target"),
            default_evaluator_slug=optional_str_metadata(metadata, "default_evaluator_slug"),
            final_score=score,
            total_cost_usd=total_cost_usd,
            error_message=None,
        )


def _increment_status_count(counts: CohortStatusCountsDto, status: str) -> None:
    match status:
        case "pending":
            counts.pending += 1
        case "executing":
            counts.executing += 1
        case "evaluating":
            counts.evaluating += 1
        case "completed":
            counts.completed += 1
        case "failed":
            counts.failed += 1


def _score_value(run: RunRecord) -> float | None:
    """Choose the score field used for cohort aggregates."""
    summary = run.parsed_summary()
    if not summary:
        return None
    norm = summary.get("normalized_score")
    if norm is not None:
        return float(norm)
    final = summary.get("final_score")
    if final is not None:
        return float(final)
    return None


def _definitions_for_cohort(session: Session, cohort_id: UUID) -> list[ExperimentDefinition]:
    return [
        definition
        for definition in session.exec(select(ExperimentDefinition)).all()
        if cohort_id_from_metadata(definition.parsed_metadata()) == cohort_id
    ]


def _instance_count(session: Session, definition_id: UUID) -> int:
    return len(
        list(
            session.exec(
                select(ExperimentDefinitionInstance.id).where(
                    ExperimentDefinitionInstance.experiment_definition_id == definition_id
                )
            )
        )
    )


def _rubric_status_summary(summaries: list[EvaluationSummary]) -> RubricStatusSummary:
    statuses: list[str] = []
    evaluator_names: list[str] = []
    for summary in summaries:
        evaluator_names.append(summary.evaluator_name)
        statuses.extend(result.status for result in summary.criterion_results)

    passed = statuses.count("passed")
    failed = statuses.count("failed")
    errored = statuses.count("errored")
    skipped = statuses.count("skipped")
    status = "none"
    if errored:
        status = "errored"
    elif failed:
        status = "failing"
    elif passed:
        status = "passing"

    return RubricStatusSummary(
        status=status,
        total_criteria=len(statuses),
        passed=passed,
        failed=failed,
        errored=errored,
        skipped=skipped,
        criterion_statuses=statuses,
        evaluator_names=evaluator_names,
    )


def _experiment_row_status(
    experiment_status: str,
    counts: CohortStatusCountsDto,
    total_runs: int,
) -> str:
    if total_runs == 0:
        return experiment_status
    active_runs = counts.pending + counts.executing + counts.evaluating
    if active_runs > 0:
        return experiment_status
    if counts.failed == total_runs:
        return "failed"
    if counts.completed == total_runs:
        return "completed"
    if counts.failed > 0 and counts.completed > 0:
        return "completed_with_failures"
    return experiment_status


deprecated_cohort_compatibility_service = DeprecatedCohortCompatibilityService()


async def emit_deprecated_cohort_updated_for_run(run_id: UUID) -> None:
    """Refresh and publish the deprecated cohort summary for a run, if any."""
    from ergon_core.core.views.dashboard_events.cohorts import cohort_updated_event_from_summary

    cohort_id = deprecated_cohort_compatibility_service.cohort_id_for_run(run_id)
    if cohort_id is None:
        return

    deprecated_cohort_compatibility_service.recompute(cohort_id)
    summary = deprecated_cohort_compatibility_service.get_summary(cohort_id)
    if summary is None:
        return

    await get_dashboard_event_publisher().publish(cohort_updated_event_from_summary(summary))
