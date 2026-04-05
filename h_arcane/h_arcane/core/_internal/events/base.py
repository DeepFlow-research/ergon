"""Base class for strongly-typed Inngest event contracts.

Each event contract defines:
- `name`: The Inngest event name (e.g., "task/ready")
- Pydantic fields: The event payload schema

Usage:
    class TaskReadyEvent(InngestEventContract):
        name: ClassVar[str] = "task/ready"

        run_id: str
        experiment_id: str
        task_id: str

    # Sending:
    await inngest_client.send(
        inngest.Event(
            name=TaskReadyEvent.name,
            data=TaskReadyEvent(run_id=..., experiment_id=..., task_id=...).model_dump(),
        )
    )

    # Receiving (in Inngest function):
    event_data = TaskReadyEvent(**ctx.event.data)
"""

from typing import ClassVar

from pydantic import BaseModel


class InngestEventContract(BaseModel):
    """
    Base class for Inngest event contracts.

    Subclasses must define:
    - `name`: ClassVar[str] - The Inngest event name
    - Pydantic fields for the event payload

    This provides:
    - Type safety for event payloads
    - Single source of truth for event name + schema
    - Clear contracts between event producers and consumers
    """

    name: ClassVar[str]

    model_config = {"extra": "forbid"}  # Catch typos in field names
