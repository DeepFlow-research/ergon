"""Runtime resource view boundary.

The current resource operations still live on ``WorkflowService`` during the
PR11 move, but imports should target ``RuntimeResourceService`` from this
module when new runtime resource callers are added.
"""

from ergon_core.core.application.runtime.sample_lifecycle import WorkflowService


class RuntimeResourceService(WorkflowService):
    """Resource projection facade for run/task scoped resource operations."""
