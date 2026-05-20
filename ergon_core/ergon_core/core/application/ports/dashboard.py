"""Application port for publishing already-built dashboard events."""

from typing import Protocol, runtime_checkable

from ergon_core.core.application.events.base import InngestEventContract


@runtime_checkable
class DashboardEventPublisher(Protocol):
    """Publishes dashboard event contracts without owning their construction."""

    async def publish(self, event: InngestEventContract) -> None: ...


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
