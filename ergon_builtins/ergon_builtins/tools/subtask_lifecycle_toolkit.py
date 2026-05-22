"""Deprecated compatibility import for ``ergon_builtins.toolkits.subagents``."""

from ergon_builtins.toolkits.subagents.models import (
    AddSubtaskToolResponse,
    AddSubtaskToolSuccess,
    CancelTaskToolResponse,
    CancelTaskToolSuccess,
    GetSubtaskToolResponse,
    GetSubtaskToolSuccess,
    ListSubtasksToolResponse,
    ListSubtasksToolSuccess,
    PlanSubtasksToolResponse,
    PlanSubtasksToolSuccess,
    RefineTaskToolResponse,
    RefineTaskToolSuccess,
    RestartTaskToolResponse,
    RestartTaskToolSuccess,
    ToolFailure,
)
from ergon_builtins.toolkits.subagents.toolkit import (
    SubtaskLifecycleToolkit,
    build_subtask_lifecycle_tools,
)

__all__ = [
    "AddSubtaskToolResponse",
    "AddSubtaskToolSuccess",
    "CancelTaskToolResponse",
    "CancelTaskToolSuccess",
    "GetSubtaskToolResponse",
    "GetSubtaskToolSuccess",
    "ListSubtasksToolResponse",
    "ListSubtasksToolSuccess",
    "PlanSubtasksToolResponse",
    "PlanSubtasksToolSuccess",
    "RefineTaskToolResponse",
    "RefineTaskToolSuccess",
    "RestartTaskToolResponse",
    "RestartTaskToolSuccess",
    "SubtaskLifecycleToolkit",
    "ToolFailure",
    "build_subtask_lifecycle_tools",
]
