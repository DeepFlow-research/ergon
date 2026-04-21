"""Response DTOs returned to the LLM by task management tools."""

from uuid import UUID

from pydantic import BaseModel


class AddTaskResponse(BaseModel):
    success: bool
    node_id: UUID | None = None
    task_slug: str | None = None
    error: str | None = None


class AbandonTaskResponse(BaseModel):
    success: bool
    node_id: UUID | None = None
    previous_status: str | None = None
    error: str | None = None


class RefineTaskResponse(BaseModel):
    success: bool
    node_id: UUID | None = None
    old_description: str | None = None
    new_description: str | None = None
    error: str | None = None
