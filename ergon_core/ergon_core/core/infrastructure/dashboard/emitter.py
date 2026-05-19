"""Transport-only dashboard event publisher."""

import logging

import inngest

from ergon_core.core.application.events.base import InngestEventContract
from ergon_core.core.infrastructure.inngest.client import inngest_client

logger = logging.getLogger(__name__)


class DashboardEmitter:
    """Sends already-built dashboard events via Inngest."""

    def __init__(self, *, enabled: bool = True) -> None:
        self._enabled = enabled

    @property
    def enabled(self) -> bool:
        return self._enabled

    @enabled.setter
    def enabled(self, value: bool) -> None:
        self._enabled = value

    async def publish(self, event: InngestEventContract) -> None:
        if not self._enabled:
            return
        try:
            await inngest_client.send(
                inngest.Event(name=event.name, data=event.model_dump(mode="json"))
            )
        except Exception:  # slopcop: ignore[no-broad-except]
            logger.warning("Failed to emit %s", event.name, exc_info=True)
