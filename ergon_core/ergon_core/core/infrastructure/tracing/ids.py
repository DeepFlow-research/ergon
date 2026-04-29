"""Deterministic trace and span ID helpers."""

import hashlib
import random
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Iterator
from uuid import UUID

TRACE_FLAGS_SAMPLED = 0x01
MAX_TRACE_ID = (1 << 128) - 1
MAX_SPAN_ID = (1 << 64) - 1
EMPTY_SPAN_ID = 0

_desired_trace_id: ContextVar[int | None] = ContextVar("desired_trace_id", default=None)
_desired_span_id: ContextVar[int | None] = ContextVar("desired_span_id", default=None)


def trace_id_from_run_id(run_id: UUID) -> int:
    """Derive a deterministic 128-bit trace ID from a run UUID."""
    return int(run_id.hex, 16) & MAX_TRACE_ID


def span_id_from_key(*parts: str) -> int:
    """Derive a deterministic 64-bit span ID from arbitrary string parts."""
    digest = hashlib.sha256(":".join(parts).encode()).digest()[:8]
    return int.from_bytes(digest, "big") & MAX_SPAN_ID or 1


class DeterministicIdGenerator:
    """OTEL ID generator that supports one-shot deterministic overrides."""

    def generate_trace_id(self) -> int:
        override = _desired_trace_id.get()
        if override is not None:
            return override
        return random.getrandbits(128)

    def generate_span_id(self) -> int:
        override = _desired_span_id.get()
        if override is not None:
            return override
        return random.getrandbits(64) or 1


@contextmanager
def id_override(trace_id: int | None = None, span_id: int | None = None) -> Iterator[None]:
    trace_token = _desired_trace_id.set(trace_id) if trace_id is not None else None
    span_token = _desired_span_id.set(span_id) if span_id is not None else None
    try:
        yield
    finally:
        if span_token is not None:
            _desired_span_id.reset(span_token)
        if trace_token is not None:
            _desired_trace_id.reset(trace_token)
