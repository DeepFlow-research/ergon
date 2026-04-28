"""Helpers for serializing values into OTEL-safe attributes."""

import json
from datetime import UTC, datetime

from ergon_core.core.json_types import JsonObject, JsonValue
from ergon_core.core.settings import settings


def truncate_text(value: str | None, max_length: int | None = None) -> str | None:
    if value is None:
        return None
    limit = max_length or settings.otel_max_attribute_length
    if len(value) <= limit:
        return value
    return f"{value[:limit]}...[truncated]"


def safe_json_attribute(value: JsonValue, max_length: int | None = None) -> str:
    try:
        serialized = json.dumps(value, default=str, separators=(",", ":"))
    except (TypeError, ValueError):
        serialized = str(value)
    return truncate_text(serialized, max_length=max_length) or ""


def normalize_attributes(attributes: JsonObject | None) -> JsonObject:
    if not attributes:
        return {}
    normalized: JsonObject = {}
    for key, value in attributes.items():
        if value is None:
            continue
        if isinstance(value, (bool, int, float)):
            normalized[key] = value
        elif isinstance(value, str):
            normalized[key] = truncate_text(value)
        else:
            normalized[key] = safe_json_attribute(value)
    return normalized


def datetime_to_nanos(value: datetime) -> int:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return int(value.timestamp() * 1_000_000_000)
