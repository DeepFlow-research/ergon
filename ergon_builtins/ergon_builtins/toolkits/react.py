"""Serializable toolkit contracts for ReAct workers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from ergon_core.api import Sandbox, Task, WorkerContext
from ergon_core.core.domain.definitions import serialize_definition
from ergon_core.core.shared.json_types import JsonObject
from pydantic import BaseModel


class ReActToolkit(BaseModel, ABC):
    """Serializable spec that materializes live tools at execution time."""

    model_config = {"arbitrary_types_allowed": True, "extra": "forbid", "frozen": True}

    @abstractmethod
    def build_tools(
        self,
        *,
        task: Task,
        context: WorkerContext,
        sandbox: Sandbox,
    ) -> list[Any]:  # slopcop: ignore[no-typing-any]
        raise NotImplementedError

    def build_agent_deps(
        self,
        *,
        context: WorkerContext,
    ) -> Any | None:  # slopcop: ignore[no-typing-any]
        del context
        return None

    def to_definition(self) -> JsonObject:
        return serialize_definition(self)
