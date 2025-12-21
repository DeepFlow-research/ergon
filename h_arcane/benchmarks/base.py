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
    """Base class for benchmark-specific toolkits.
    
    Toolkits provide tools to the worker agent. The ask_stakeholder
    functionality is provided as a tool via get_tools(), not as a 
    direct method.
    """

    @property
    @abstractmethod
    def questions_asked(self) -> int:
        """Number of stakeholder questions asked so far."""
        ...

    @abstractmethod
    def get_tools(self) -> list:
        """Get list of tools available to the worker.
        
        This should include the ask_stakeholder tool.
        """
        ...
