from typing import Protocol

from pydantic import BaseModel, ConfigDict

from ergon_core.api.task import Task


class DynamicTaskFactory(Protocol):
    def child_task(
        self,
        *,
        parent: Task,
        task_slug: str,
        description: str,
    ) -> Task: ...


class CopyParentDynamicTaskFactory(BaseModel):
    """Build a dynamic child by preserving the parent's object-bound runtime shape."""

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    def child_task(
        self,
        *,
        parent: Task,
        task_slug: str,
        description: str,
    ) -> Task:
        return parent.model_copy(
            update={
                "task_slug": task_slug,
                "description": description,
                "parent_task_slug": parent.task_slug,
                "dependency_task_slugs": (),
            },
            deep=True,
        )
