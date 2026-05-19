"""Compatibility helpers for deprecated cohort metadata."""

from uuid import UUID

from ergon_core.core.application.ports.dashboard import get_dashboard_event_publisher

COHORT_METADATA_KEY = "cohort_id"


def cohort_id_from_metadata(metadata: dict) -> UUID | None:
    raw = metadata.get(COHORT_METADATA_KEY)
    if raw is None:
        return None
    if isinstance(raw, UUID):
        return raw
    if isinstance(raw, str):
        return UUID(raw)
    return None


def optional_str_metadata(metadata: dict, key: str) -> str | None:
    value = metadata.get(key)
    return value if isinstance(value, str) else None


async def emit_deprecated_cohort_updated_for_run(run_id: UUID) -> None:
    """Refresh and publish the deprecated cohort summary for a run, if any."""
    from ergon_core.core.application.read_models.cohorts import experiment_cohort_service
    from ergon_core.core.views.dashboard_events.cohorts import cohort_updated_event_from_summary

    cohort_id = experiment_cohort_service.cohort_id_for_run(run_id)
    if cohort_id is None:
        return

    experiment_cohort_service.recompute(cohort_id)
    summary = experiment_cohort_service.get_summary(cohort_id)
    if summary is None:
        return

    await get_dashboard_event_publisher().publish(cohort_updated_event_from_summary(summary))
