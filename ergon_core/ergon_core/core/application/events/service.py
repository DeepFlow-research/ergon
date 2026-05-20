"""Application service locator for dashboard event publishing."""

from ergon_core.core.application.ports import DashboardEventPublisher

_dashboard_event_publisher: DashboardEventPublisher | None = None


def set_dashboard_event_publisher(
    publisher: DashboardEventPublisher,
) -> DashboardEventPublisher:
    global _dashboard_event_publisher
    _dashboard_event_publisher = publisher
    return publisher


def get_dashboard_event_publisher() -> DashboardEventPublisher:
    if _dashboard_event_publisher is None:
        raise RuntimeError("DashboardEventPublisher has not been initialized")
    return _dashboard_event_publisher


def reset_dashboard_event_publisher() -> None:
    global _dashboard_event_publisher
    _dashboard_event_publisher = None
