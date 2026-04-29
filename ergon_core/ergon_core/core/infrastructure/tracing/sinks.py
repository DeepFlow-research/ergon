"""Process-wide trace sink factory."""

from ergon_core.core.infrastructure.tracing.noop import NoopTraceSink
from ergon_core.core.infrastructure.tracing.otel import OtelTraceSink
from ergon_core.core.infrastructure.tracing.types import TraceSink
from ergon_core.core.shared.settings import settings


def _create_sink() -> TraceSink:
    if not settings.otel_traces_enabled:
        return NoopTraceSink()
    # The operator explicitly opted in to OTEL. Refuse to silently downgrade
    # to a no-op sink, so trace exporter misconfiguration is loud.
    return OtelTraceSink()


_sink: TraceSink = _create_sink()


def get_trace_sink() -> TraceSink:
    """Return the process-wide trace sink.

    Each process (uvicorn worker, CLI invocation, test runner) gets its own
    sink created at import time. No locking needed; OTEL is stateless
    per-process and the collector handles fan-in from multiple exporters.
    """
    return _sink
