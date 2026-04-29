"""Base class for strongly-typed Inngest event contracts."""

from typing import ClassVar

from pydantic import BaseModel


class InngestEventContract(BaseModel):
    """Subclasses define name: ClassVar[str] and Pydantic payload fields.

    Single source of truth for event name + schema. Used for both
    sending (model_dump) and receiving (**ctx.event.data).
    """

    name: ClassVar[str]

    # extra="allow": Inngest injects _inngest metadata into event payloads.
    # Without this, Pydantic rejects events at parse time.
    model_config = {"extra": "allow"}
