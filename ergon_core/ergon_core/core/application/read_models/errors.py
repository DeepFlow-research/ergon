"""Read-model errors."""


class ReadModelError(Exception):
    """Base for read-model failures."""


class ResourceTooLargeError(ReadModelError):
    """A resource blob is too large for inline viewing."""

    def __init__(self, size_bytes: int, limit_bytes: int) -> None:
        super().__init__(
            f"Resource content {size_bytes} bytes exceeds viewer limit ({limit_bytes} bytes)"
        )
        self.size_bytes = size_bytes
        self.limit_bytes = limit_bytes

