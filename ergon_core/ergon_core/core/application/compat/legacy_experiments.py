"""Compatibility helpers for retired experiment-definition display metadata."""

from uuid import UUID


def cohort_id_from_metadata(metadata: dict) -> UUID | None:
    raw = metadata.get("cohort_id")
    if raw is None:
        return None
    if isinstance(raw, UUID):
        return raw
    if isinstance(raw, str):
        return UUID(raw)
    return None


def dict_metadata(metadata: dict, key: str) -> dict:
    value = metadata.get(key)
    return dict(value) if isinstance(value, dict) else {}


def optional_str_metadata(metadata: dict, key: str) -> str | None:
    value = metadata.get(key)
    return value if isinstance(value, str) else None
