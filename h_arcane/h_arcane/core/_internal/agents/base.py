"""Base classes and protocols for benchmarks."""

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Protocol
from uuid import UUID

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from h_arcane.core._internal.communication.schemas import MessageResponse


class WorkerExecutionOutput(BaseModel):
    """Structured output from worker execution.

    NOTE: This is still used by ReActWorker as output_type for Agent.
    Workers return WorkerResult (from SDK), but Agent uses this for structured extraction.
    """

    reasoning: str = Field(description="Explanation of approach and decisions made")
    output_text: str = Field(description="Text summary/output of what was accomplished")
    output_resource_ids: list[str] = Field(
        default_factory=list, description="UUIDs of resources created during execution"
    )


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

    @property
    @abstractmethod
    def model(self) -> str:
        """LLM model used by this stakeholder."""
        ...

    @property
    @abstractmethod
    def system_prompt(self) -> str:
        """System prompt describing stakeholder behavior (for logging)."""
        ...

    @abstractmethod
    async def answer(
        self,
        question: str,
        history: list["MessageResponse"] | None = None,
    ) -> str:
        """Answer a question based on benchmark context.

        Args:
            question: The current question from the worker
            history: Previous Q&A pairs in this thread (oldest first)

        Returns:
            The stakeholder's answer
        """
        ...


class BaseToolkit(ABC):
    """Base class for benchmark-specific toolkits.

    Toolkits provide tools to the worker agent and provide access
    to the stakeholder for questions.
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

    @abstractmethod
    async def ask_stakeholder(self, question: str) -> str:
        """Ask the stakeholder a question.

        Args:
            question: The question to ask

        Returns:
            The stakeholder's response
        """
        ...

    @abstractmethod
    def get_qa_history(self) -> list:
        """Return Q&A history for inclusion in WorkerResult.

        Called by worker after execution to collect trace data.
        Returns list of QAExchange objects (using list to avoid circular import).
        """
        ...
