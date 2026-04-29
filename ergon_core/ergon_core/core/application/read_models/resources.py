"""Resource read-model limits and guards."""

from ergon_core.core.application.read_models.errors import ResourceTooLargeError

RESOURCE_CONTENT_MAX_BYTES: int = 10 * 1024 * 1024


def require_viewable_resource_size(size_bytes: int) -> None:
    if size_bytes > RESOURCE_CONTENT_MAX_BYTES:
        raise ResourceTooLargeError(size_bytes, RESOURCE_CONTENT_MAX_BYTES)
