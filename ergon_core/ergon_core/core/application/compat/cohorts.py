"""Compatibility helpers for deprecated cohort metadata."""

from uuid import UUID

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
