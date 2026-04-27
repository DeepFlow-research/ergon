"""Structured runtime error payloads for persisted execution failures."""

import traceback
from collections.abc import Mapping
from typing import Any

from ergon_core.api.json_types import JsonObject
from pydantic import BaseModel, Field


class RuntimeErrorPayload(BaseModel):
    """Persisted shape for task execution failures."""

    message: str
    exception_type: str
    phase: str
    stack: str
    context: dict[str, str] = Field(default_factory=dict)


def build_error_json(
    exc: BaseException,
    *,
    phase: str,
    context: Mapping[str, Any] | None = None,
) -> JsonObject:
    """Return stack-rich, queryable error details for PG persistence."""
    payload = RuntimeErrorPayload(
        message=str(exc),
        exception_type=type(exc).__name__,
        phase=phase,
        stack="".join(traceback.format_exception(type(exc), exc, exc.__traceback__)),
        context={key: str(value) for key, value in (context or {}).items()},
    )
    return payload.model_dump(mode="json")
