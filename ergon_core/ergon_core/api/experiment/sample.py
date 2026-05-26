"""Concrete sample authoring object."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator

from ergon_core.api.benchmark import Task


class Sample(BaseModel):
    """A selected runnable unit containing concrete public ``Task`` objects."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    name: str
    sample_key: str
    environment_name: str
    tasks: Sequence[Task]
    sample_ref: dict[str, JsonValue] = Field(default_factory=dict)
    source_metadata: dict[str, JsonValue] = Field(default_factory=dict)
    metadata: dict[str, JsonValue] = Field(default_factory=dict)

    @classmethod
    def from_tasks(
        cls,
        *,
        name: str,
        sample_key: str,
        environment_name: str,
        tasks: Sequence[Task],
        sample_ref: Mapping[str, JsonValue] | None = None,
        source_metadata: Mapping[str, JsonValue] | None = None,
        metadata: Mapping[str, JsonValue] | None = None,
    ) -> "Sample":
        return cls(
            name=name,
            sample_key=sample_key,
            environment_name=environment_name,
            tasks=list(tasks),
            sample_ref=dict(sample_ref or {}),
            source_metadata=dict(source_metadata or {}),
            metadata=dict(metadata or {}),
        )

    @model_validator(mode="after")
    def _validate_on_create(self) -> "Sample":
        self.validate_runnable()
        return self

    def validate_runnable(self) -> None:
        if not self.tasks:
            raise ValueError("Sample requires at least one task")
        keys = [task.task_slug for task in self.tasks]
        if len(keys) != len(set(keys)):
            raise ValueError("Sample task keys must be unique")
        known = set(keys)
        for task in self.tasks:
            for dependency in task.dependency_task_slugs:
                if dependency not in known:
                    raise ValueError(f"Unknown dependency task key: {dependency}")

    def task_count(self) -> int:
        return len(self.tasks)

    def root_tasks(self) -> Sequence[Task]:
        return [task for task in self.tasks if not task.dependency_task_slugs]

    def task_by_key(self, key: str) -> Task:
        for task in self.tasks:
            if task.task_slug == key:
                return task
        raise KeyError(key)
