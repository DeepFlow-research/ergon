"""Dashboard emission module — re-exports for convenience."""

from ergon_core.core.infrastructure.dashboard.emitter import DashboardEmitter
from ergon_core.core.infrastructure.dashboard.provider import (
    get_dashboard_emitter,
    init_dashboard_emitter,
    reset_dashboard_emitter,
    set_dashboard_emitter,
)

__all__ = [
    "DashboardEmitter",
    "get_dashboard_emitter",
    "init_dashboard_emitter",
    "reset_dashboard_emitter",
    "set_dashboard_emitter",
]
