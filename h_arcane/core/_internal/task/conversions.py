"""Conversion utilities between SDK types and DB types.

These functions bridge the gap between user-facing SDK types
and the internal database models.
"""

from uuid import UUID

from h_arcane.core._internal.db.models import ResourceRecord
from h_arcane.core.task import Resource


def db_resource_to_sdk(db_resource: ResourceRecord) -> Resource:
    """Convert DB ResourceRecord to SDK Resource.

    Args:
        db_resource: The database resource record

    Returns:
        SDK Resource with path and name populated
    """
    return Resource(
        path=db_resource.file_path,
        name=db_resource.name,
        mime_type_override=db_resource.mime_type,
    )


def db_resources_to_sdk(db_resources: list[ResourceRecord]) -> list[Resource]:
    """Convert a list of DB ResourceRecords to SDK Resources.

    Args:
        db_resources: List of database resource records

    Returns:
        List of SDK Resources
    """
    return [db_resource_to_sdk(r) for r in db_resources]


def sdk_resource_to_db_dict(
    sdk_resource: Resource,
    run_id: UUID,
    task_id: UUID,
    experiment_id: UUID,
    is_input: bool = False,
) -> dict:
    """Convert SDK Resource to dict suitable for DB ResourceRecord creation.

    Args:
        sdk_resource: The SDK resource
        run_id: The run UUID
        task_id: The task UUID
        experiment_id: The experiment UUID
        is_input: Whether this is an input resource (vs output)

    Returns:
        Dict with fields for ResourceRecord creation
    """
    return {
        "run_id": run_id,
        "experiment_id": experiment_id,
        "task_id": str(task_id),
        "name": sdk_resource.name,
        "file_path": str(sdk_resource.path) if sdk_resource.path else "",
        "mime_type": sdk_resource.mime_type,
        "is_input": is_input,
        # size_bytes, preview_text would be computed when actually saving the file
    }
