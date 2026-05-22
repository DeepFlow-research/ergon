"""Application port for publishing already-built dashboard events."""

from typing import Any, Protocol, runtime_checkable


class DashboardEventContract(Protocol):
    """Structural contract for already-built dashboard events."""

    name: str

    def model_dump(self, *, mode: str = "python") -> dict[str, Any]: ...


@runtime_checkable
class DashboardEventPublisher(Protocol):
    """Publishes dashboard event contracts without owning their construction."""

    async def publish(self, event: DashboardEventContract) -> None: ...
