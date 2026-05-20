"""Launch helpers for getting-started examples."""

from uuid import UUID


def first_run_id(run_result: object) -> UUID:
    """Return the first launched run id from an Ergon launch result."""
    run_ids = getattr(run_result, "run_ids")
    return run_ids[0]
