"""
BaseWorker protocol for task execution.

This is the PUBLIC API for worker implementations.
Users implement this protocol to create custom workers.

Usage:
    from h_arcane import BaseWorker, Task, WorkerContext, WorkerResult
    from h_arcane.core._internal.db.models import Action

    class MyWorker(BaseWorker):
        def __init__(self, model: str, tools: list):
            self.id = uuid4()
            self.name = "my_worker"
            self.model = model
            self.tools = tools
            self.system_prompt = "You are a helpful assistant..."

        async def execute(self, task: Task, context: WorkerContext) -> WorkerResult:
            # Record actions during execution
            action = Action(action_type="read_file", input='{"path": "data.csv"}')
            ...
            return WorkerResult(actions=[action], ...)
"""

from __future__ import annotations

from abc import abstractmethod
from typing import TYPE_CHECKING, Any, Callable, Protocol, runtime_checkable
from uuid import UUID

from pydantic import BaseModel, Field

from h_arcane.core._internal.db.models import Action

if TYPE_CHECKING:
    from h_arcane.core.task import Resource, Task


class NamedTool(Protocol):
    """Protocol for tool objects that have a name attribute (e.g., OpenAI Tool, LangChain BaseTool)."""

    name: str


# Tools can be:
# - Callable (function with __name__)
# - NamedTool (object with .name attribute)
# - str (tool name directly)
Tool = Callable[..., Any] | NamedTool | str


@runtime_checkable
class BaseWorker(Protocol):
    """
    Protocol that all worker implementations must follow.

    Workers are self-contained with their tools, model config, and execution logic.
    Users pass worker instances to Task.assigned_to.

    Required properties:
        id: Unique identifier for this worker instance
        name: Human-readable name (e.g., "analyst", "writer")
        model: LLM model to use (e.g., "gpt-4o")
        tools: List of tools/functions the worker can use
        system_prompt: Instructions for the worker

    Example implementation:
        class ReactWorker(BaseWorker):
            def __init__(self, model: str, tools: list, system_prompt: str = ""):
                self.id = uuid4()
                self.name = "react_worker"
                self.model = model
                self.tools = tools
                self.system_prompt = system_prompt

            async def execute(self, task: Task, context: WorkerContext) -> WorkerResult:
                # Implementation using OpenAI Agents SDK, etc.
                ...
    """

    # Required properties
    id: UUID
    name: str
    model: str
    tools: list[Tool]
    system_prompt: str

    @abstractmethod
    async def execute(self, task: "Task", context: "WorkerContext") -> "WorkerResult":
        """
        Execute the given task.

        Args:
            task: The task to execute (contains description, resources, etc.)
            context: Execution context (sandbox, run_id, etc.)

        Returns:
            WorkerResult with outputs, actions, and status
        """
        ...


# =============================================================================
# Execution Context and Result
# =============================================================================


class QAExchange(BaseModel):
    """A single question-answer exchange with stakeholder."""

    question: str
    answer: str


class WorkerContext(BaseModel):
    """
    Context provided to workers during execution.

    This contains everything a worker needs to execute a task,
    including sandbox access, input resources, and run metadata.
    """

    run_id: UUID = Field(
        ...,
        description="The current run's UUID",
    )
    task_id: UUID = Field(
        ...,
        description="The current task's UUID",
    )
    sandbox: Any = Field(
        default=None,
        description="E2B sandbox instance for code execution",
    )
    input_resources: list["Resource"] = Field(
        default_factory=list,
        description="Input resources (files, data) available to the worker",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional context (benchmark-specific data, etc.)",
    )

    # For workers that need benchmark tools (e.g., ReActWorker)
    #TODO: tighten type
    toolkit: Any = Field(
        default=None,
        description="Benchmark toolkit with tools and stakeholder access (BaseToolkit)",
    )
    agent_config_id: UUID | None = Field(
        default=None,
        description="Agent config ID for action persistence",
    )

    model_config = {"arbitrary_types_allowed": True}


class WorkerResult(BaseModel):
    """
    Result returned by a worker's execute() method.

    This captures everything needed to persist the execution:
    - actions: Tool call trace (list of Action DB models)
    - outputs: Output files/resources (list of Resource)
    - output_text: Text summary/answer
    - success/error: Execution status

    Note: Action instances don't need run_id/agent_id/action_num set -
    the persistence layer fills those in.
    """

    success: bool = Field(
        default=True,
        description="Whether execution succeeded",
    )
    actions: list[Action] = Field(
        default_factory=list,
        description="Ordered list of actions (tool calls) taken during execution",
    )
    outputs: list["Resource"] = Field(
        default_factory=list,
        description="Output resources (files) produced by the worker",
    )
    output_text: str | None = Field(
        default=None,
        description="Final text output (summary, answer, etc.)",
    )
    reasoning: str | None = Field(
        default=None,
        description="Worker's reasoning/thought process (if available)",
    )
    qa_exchanges: list[QAExchange] = Field(
        default_factory=list,
        description="Q&A exchanges with stakeholder (for benchmark workers)",
    )
    error: str | None = Field(
        default=None,
        description="Error message if execution failed",
    )

    model_config = {"arbitrary_types_allowed": True}
