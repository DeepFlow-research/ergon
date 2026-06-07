"""Launch helpers for getting-started examples."""

from uuid import UUID


def first_sample_id(sample_result: object) -> UUID:
    """Return the first launched sample id from an Ergon launch result."""
    sample_ids = getattr(sample_result, "sample_ids")
    return sample_ids[0]
