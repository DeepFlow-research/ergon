"""Base classes and protocols for benchmarks."""

from abc import ABC, abstractmethod
from typing import Protocol
from uuid import UUID


class BenchmarkLoader(Protocol):
    """Protocol for loading benchmark data."""

    def load_tasks(self, limit: int | None = None) -> list[dict]:
        """Load tasks from benchmark dataset."""
        ...

    def load_to_database(self, tasks: list[dict]) -> list[UUID]:
        """Load tasks into database as Experiment records."""
        ...


class BaseStakeholder(ABC):
    """Base class for benchmark-specific stakeholders."""

    @abstractmethod
    async def answer(self, question: str) -> str:
        """Answer a question based on benchmark context."""
        ...


class BaseToolkit(ABC):
    """Base class for benchmark-specific toolkits."""

    @abstractmethod
    async def ask_stakeholder(self, question: str) -> str:
        """Ask the stakeholder a question."""
        ...

    @abstractmethod
    def get_tools(self) -> list:
        """Get list of tools available to the worker."""
        ...
