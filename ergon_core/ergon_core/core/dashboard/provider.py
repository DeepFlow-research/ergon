"""Process-level DashboardEmitter provider.

FastAPI lifespan owns construction. Runtime code that is not running inside a
request can retrieve the initialized process instance from here.
"""

from ergon_core.core.dashboard.emitter import DashboardEmitter

_dashboard_emitter: DashboardEmitter | None = None


def init_dashboard_emitter(*, enabled: bool = True) -> DashboardEmitter:
    """Create and install the process DashboardEmitter instance."""
    return set_dashboard_emitter(DashboardEmitter(enabled=enabled))


def set_dashboard_emitter(emitter: DashboardEmitter) -> DashboardEmitter:
    """Install an already-created DashboardEmitter instance."""
    global _dashboard_emitter
    _dashboard_emitter = emitter
    return _dashboard_emitter


def get_dashboard_emitter() -> DashboardEmitter:
    """Return the process DashboardEmitter, requiring startup initialization."""
    if _dashboard_emitter is None:
        raise RuntimeError("DashboardEmitter has not been initialized")
    return _dashboard_emitter


def reset_dashboard_emitter() -> None:
    """Clear the process DashboardEmitter instance."""
    global _dashboard_emitter
    _dashboard_emitter = None
