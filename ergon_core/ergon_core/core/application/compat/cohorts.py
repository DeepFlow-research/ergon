"""Compatibility helpers for deprecated cohort metadata."""

from typing import Any
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
