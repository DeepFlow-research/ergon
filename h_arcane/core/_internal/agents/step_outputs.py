"""Step output models for agents inngest functions.

These are service contracts for step.run return types - they define
the shape of data passed between steps within a single Inngest function.
"""

from pydantic import BaseModel

from h_arcane.core._internal.db.models import ResourceRecord


class InputResourcesResult(BaseModel):
    """Result of load-input-resources step."""

    resources: list[ResourceRecord]
