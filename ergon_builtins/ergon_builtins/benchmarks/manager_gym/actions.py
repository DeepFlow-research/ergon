"""Pinned MAG action fields; execution is implemented with native Ergon APIs."""

from typing import Any, Literal
from uuid import UUID
import json
from pydantic import BaseModel, Field, field_validator


class ActionResult(BaseModel):
    """Structured result returned by manager actions.

    Example:
        ```python
        ActionResult(
            action_type="assign_task",
            summary="Assigned T123 to ai_writer",
            kind="mutation",
            data={"task_id": "...", "agent_id": "ai_writer"},
            timestep=3,
            success=True,
        )
        ```
    """

    action_type: Literal[
        "assign_task",
        "assign_all_pending_tasks",
        "create_task",
        "remove_task",
        "send_message",
        "noop",
        "get_workflow_status",
        "get_available_agents",
        "get_pending_tasks",
        "refine_task",
        "add_task_dependency",
        "remove_task_dependency",
        "failed_action",
        "inspect_task",
        "request_end_workflow",
        "decompose_task",
        "assign_tasks_to_agents",
    ] = Field(description="Type of action result")
    summary: str = Field(description="Short summary of what happened / info returned")
    kind: Literal[
        "mutation", "info", "noop", "message", "inspection", "failed_action", "unknown"
    ] = Field(description="Type of action result")
    data: dict[str, Any] = Field(
        description="Optional structured payload for follow-up use (empty if not applicable)"
    )
    timestep: int | None = Field(
        default=None, description="Timestep of the action, set by the engine"
    )
    success: bool = Field(default=True, description="Whether the action succeeded (set by execute)")


class BaseManagerAction(BaseModel):
    """
    Base class for all manager actions.

    All action classes must inherit from this and implement the execute method.
    This ensures type safety and consistent execution interface.
    """

    reasoning: str = Field(
        description="Concise 2–3 sentence rationale for the chosen action",
        examples=["Agent idle, task READY, skill match found → assigning ai_writer."],
    )


class AssignTaskAction(BaseManagerAction):
    """Assign a ready task to an available, appropriate agent.

    Use when:
    - A validated task is READY and a matching agent has capacity
    - You have confirmed the task does not require human approval/sign-off

    Examples:
    - Assign "Draft technical memo" to `ai_analyst_1` (READY and cheap to parallelize)
    - Assign "Generate regulatory filing draft" to `ai_writer` after requirements clarified

    Never assign to AI when the task involves approval, sign-off, certification, stakeholder-facing presentation, or strategic decision-making; these must go to a human agent.
    """

    action_type: Literal["assign_task"] = "assign_task"
    task_id: str = Field(description="ID of the task to assign")
    agent_id: str = Field(description="ID of the agent to assign the task to")


class CreateTaskAction(BaseManagerAction):
    """Create a new actionable task to advance the workflow.

    Use when:
    - Agents are idle and no READY tasks exist (pipeline gap)
    - You need explicit artifacts to satisfy constraints or evaluators
    - You want to introduce approvals/reviews as tasks to route to humans

    Examples:
    - Create "Stakeholder approval: v1 solution proposal" (assign to human approver)
    - Create "Compliance review: data lineage evidence" to satisfy a hard constraint
    - Create "Prepare stakeholder presentation" (later assign to the relevant human)
    - Create "Risk register update" to document tradeoffs and decisions
    """

    action_type: Literal["create_task"] = "create_task"
    name: str = Field(description="Clear, descriptive task name")
    description: str = Field(
        description="Detailed task description including objectives and deliverables"
    )
    estimated_duration_hours: float = Field(description="Estimated time to complete the task")
    estimated_cost: float = Field(description="Estimated cost to complete the task")


class RemoveTaskAction(BaseManagerAction):
    """Remove a task that is out of scope, duplicated, or obsolete; use to reduce clutter and eliminate work that no longer contributes to objectives."""

    action_type: Literal["remove_task"] = "remove_task"
    task_id: UUID = Field(description="ID of the task to remove")


class SendMessageAction(BaseManagerAction):
    """Send a direct or broadcast coordination message.

    Use to:
    - Elicit preference tradeoffs (quality vs speed vs cost) without revealing hidden rubrics
    - Request review/approval or stakeholder acceptance
    - Clarify requirements or confirm scope changes
    - Inform task agents about the manner in which they should proceed, give feedback, seek information on how they intend to work on tasks, ect.

    Examples:
    - To stakeholder: "Could you prioritize speed vs quality for the next milestone (choose one)?"
    - To stakeholder: "Please confirm: Is v1 acceptable to ship as-is, or should we add a validation step?"
    - Broadcast: "All agents: pause work on feature X pending stakeholder decision."

    Note: Messaging has communication/oversight costs in evaluators; ask crisp, high-value questions.
    """

    action_type: Literal["send_message"] = "send_message"
    content: str = Field(description="Message content")
    receiver_id: str | None = Field(description="Specific receiver ID, or None for broadcast")


class NoOpAction(BaseManagerAction):
    """
    Deliberately take no action; use only when observation is required and no safe or productive action is available.
    """

    action_type: Literal["noop"] = "noop"


class GetWorkflowStatusAction(BaseManagerAction):
    """
    Inspect overall workflow health and key metrics; use to inform planning when choosing between assignment, task creation, or optimization.
    """

    action_type: Literal["get_workflow_status"] = "get_workflow_status"


class GetAvailableAgentsAction(BaseManagerAction):
    """List currently available agents and capacity; use when selecting an assignee or verifying idle capacity for immediate deployment."""

    action_type: Literal["get_available_agents"] = "get_available_agents"


class GetPendingTasksAction(BaseManagerAction):
    """List tasks in PENDING state awaiting assignment; use to triage the backlog when none are currently selected for assignment."""

    action_type: Literal["get_pending_tasks"] = "get_pending_tasks"


class RefineTaskAction(BaseManagerAction):
    """Update a task’s instructions, scope, or estimates.

    Use to:
    - Remove ambiguity and add acceptance criteria
    - Adjust scope, estimates, or add manager instructions
    - Incorporate stakeholder feedback or clarifications

    Examples:
    - Add acceptance criteria: "Include A/B test metrics and success threshold >= 2% uplift"
    - Tighten scope: rename to "Draft 2-page summary (exec audience)"
    - Add manager instructions for assignee
    """

    action_type: Literal["refine_task"] = "refine_task"
    task_id: UUID = Field(description="ID of the task to refine")
    new_name: str | None = Field(description="Updated task name (optional)")
    new_description: str | None = Field(
        description="Updated task description with refined instructions"
    )
    new_estimated_duration: float | None = Field(description="Updated duration estimate in hours")
    new_estimated_cost: float | None = Field(description="Updated cost estimate")
    additional_instructions: str | None = Field(
        description="Additional specific instructions for the assigned agent"
    )


class AddTaskDependencyAction(BaseManagerAction):
    """Create a prerequisite relationship (A must finish before B starts); use to enforce correct sequencing and protect the critical path."""

    action_type: Literal["add_task_dependency"] = "add_task_dependency"
    prerequisite_task_id: UUID = Field(description="ID of the task that must complete first")
    dependent_task_id: UUID = Field(description="ID of the task that depends on the prerequisite")


class RemoveTaskDependencyAction(BaseManagerAction):
    """
    Remove an obsolete or incorrect prerequisite link; use when sequencing is no longer required or was added in error.

    Will return a summary of the dependency removed
    """

    action_type: Literal["remove_task_dependency"] = "remove_task_dependency"
    prerequisite_task_id: UUID = Field(description="ID of the prerequisite task")
    dependent_task_id: UUID = Field(description="ID of the dependent task")


class InspectTaskAction(BaseManagerAction):
    """
    Review a specific task’s current status and outputs; use to investigate blockers, quality, or progress without changing state.

    Will return a summary of the task's status and the outputs, no state changes are made to the workflow.
    """

    action_type: Literal["inspect_task"] = "inspect_task"
    task_id: UUID = Field(description="ID of the task to inspect in detail")


class DecomposeTaskAction(BaseManagerAction):
    """Break a complex task into smaller subtasks via AI.

    Will return a summary of the decomposition and the subtasks created for the task

    Use when:
    - A task is too broad or ambiguous
    - Parallelization would increase throughput
    - Sequencing benefits from explicit dependencies

    Examples:
    - Split "Regulatory filing" into "Collect artifacts" -> "Draft sections" -> "Human approval"
    - Split "Model training" into data prep, training, evaluation, and packaging
    """

    action_type: Literal["decompose_task"] = "decompose_task"
    task_id: UUID = Field(..., description="UUID of the task id to decompose")


class RequestEndWorkflowAction(BaseManagerAction):
    """Request that the workflow end as soon as possible.

    Use when:
    - All required atomic tasks are completed and further work offers negligible utility
    - The stakeholder explicitly accepts the deliverables
    - Time/budget constraints imply continued work would reduce overall utility

    This action signals the engine via the communication service; the engine will terminate on the next check cycle.
    """

    action_type: Literal["request_end_workflow"] = "request_end_workflow"
    reason: str | None = Field(
        description="Optional short reason for requesting the workflow to end"
    )


ManagerAction = (
    AssignTaskAction
    | CreateTaskAction
    | RemoveTaskAction
    | SendMessageAction
    | NoOpAction
    | GetWorkflowStatusAction
    | GetAvailableAgentsAction
    | GetPendingTasksAction
    | RefineTaskAction
    | AddTaskDependencyAction
    | RemoveTaskDependencyAction
    | InspectTaskAction
    | DecomposeTaskAction
)


class ManagerDecision(BaseModel):
    reasoning: str
    action: ManagerAction = Field(discriminator="action_type")

    @field_validator("action", mode="before")
    @classmethod
    def decode_action(cls, value: object) -> object:
        # The standing Qwen tool parser returns nested JSON as a JSON string.
        # Decode that transport representation, then run the unchanged union
        # validation; malformed JSON and unknown actions still fail explicitly.
        return json.loads(value) if isinstance(value, str) else value
