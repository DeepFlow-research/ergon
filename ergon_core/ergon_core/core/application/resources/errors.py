"""Resource application errors."""

from uuid import UUID


class RunResourceNotFoundError(LookupError):
    """Raised when a run resource row cannot be found."""

    def __init__(self, resource_id: UUID) -> None:
        super().__init__(f"RunResource not found: {resource_id}")
        self.resource_id = resource_id
