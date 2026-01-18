"""Step output models for evaluation inngest functions.

These are service contracts for step.run return types - they define
the shape of data passed between steps within a single Inngest function.
"""

from pydantic import BaseModel

from h_arcane.core._internal.db.models import Resource


class ResourceListResult(BaseModel):
    """Result of load-resources step."""

    resources: list[Resource]
