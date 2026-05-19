"""Response models for subagent lifecycle tools."""

from typing import Literal

from ergon_core.core.application.runtime.task_models import SubtaskInfo
from ergon_core.core.persistence.shared.types import NodeId, TaskSlug
from pydantic import BaseModel


class ToolFailure(BaseModel):
    kind: Literal["failure"] = "failure"
    error: str

    model_config = {"frozen": True}


class AddSubtaskToolSuccess(BaseModel):
    kind: Literal["success"] = "success"
    node_id: NodeId
    task_slug: TaskSlug
    status: str

    model_config = {"frozen": True}


type AddSubtaskToolResponse = AddSubtaskToolSuccess | ToolFailure


class PlanSubtasksToolSuccess(BaseModel):
    kind: Literal["success"] = "success"
    nodes: dict[TaskSlug, NodeId]
    roots: list[TaskSlug]

    model_config = {"frozen": True}


type PlanSubtasksToolResponse = PlanSubtasksToolSuccess | ToolFailure


class CancelTaskToolSuccess(BaseModel):
    kind: Literal["success"] = "success"
    node_id: NodeId
    old_status: str
    cascaded_count: int

    model_config = {"frozen": True}


type CancelTaskToolResponse = CancelTaskToolSuccess | ToolFailure


class RefineTaskToolSuccess(BaseModel):
    kind: Literal["success"] = "success"
    node_id: NodeId
    old_description: str
    new_description: str

    model_config = {"frozen": True}


type RefineTaskToolResponse = RefineTaskToolSuccess | ToolFailure


class RestartTaskToolSuccess(BaseModel):
    kind: Literal["success"] = "success"
    node_id: NodeId
    old_status: str
    invalidated_node_ids: list[NodeId]

    model_config = {"frozen": True}


type RestartTaskToolResponse = RestartTaskToolSuccess | ToolFailure


class ListSubtasksToolSuccess(BaseModel):
    kind: Literal["success"] = "success"
    subtasks: list[SubtaskInfo]

    model_config = {"frozen": True}


type ListSubtasksToolResponse = ListSubtasksToolSuccess | ToolFailure


class GetSubtaskToolSuccess(BaseModel):
    kind: Literal["success"] = "success"
    node_id: NodeId
    task_slug: str
    description: str
    status: str
    depends_on: list[NodeId]
    output: str | None
    error: str | None

    model_config = {"frozen": True}


type GetSubtaskToolResponse = GetSubtaskToolSuccess | ToolFailure


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
    "ToolFailure",
]
