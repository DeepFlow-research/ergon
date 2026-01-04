"""Base classes and protocols for benchmarks."""

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Protocol
from uuid import UUID

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from h_arcane.core.db.models import Resource
    from h_arcane.core.communication.schemas import MessageResponse


class WorkerExecutionOutput(BaseModel):
    """Structured output from worker execution."""

    reasoning: str = Field(description="Explanation of approach and decisions made")
    output_text: str = Field(description="Text summary/output of what was accomplished")
    output_resource_ids: list[str] = Field(
        default_factory=list, description="UUIDs of resources created during execution"
    )


class BaseWorker(Protocol):
    """Protocol for worker agents.

    Workers execute tasks using a toolkit and return structured output.
    """

    async def execute(
        self,
        run_id: UUID,
        task_description: str,
        input_resources: list["Resource"],
        toolkit: "BaseToolkit",
    ) -> WorkerExecutionOutput:
        """Execute a task and return structured output.

        Args:
            run_id: The run ID
            task_description: Task description
            input_resources: List of input resources
            toolkit: Toolkit with tools for the worker

        Returns:
            WorkerExecutionOutput with reasoning, output_text, and output_resource_ids
        """
        ...


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
