"""Pinned MAG authoring records and rubric projection; never an execution scheduler.

Adapted from DeepFlow-research/manager_agent_gym at 3f7a5d4af1d31abaedbedd525a0090452926fef4.
See NOTICE. Scenario factories keep their original callable closures and prompts.
Workflow readiness/dispatch/graph validation methods are deliberately not included.
"""

from __future__ import annotations
import logging
from datetime import datetime
from enum import Enum
from typing import Any, Callable, List, Set, Literal
from uuid import UUID, uuid4
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from .prompts.worker import PERSONA_ROLEPLAY_TEMPLATE

logger = logging.getLogger(__name__)


class TaskStatus(str, Enum):
    """Status of a task in the workflow."""

    PENDING = "pending"
    READY = "ready"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    UNKNOWN = "unknown"


class Resource(BaseModel):
    """Workflow resource model.

    Represents inputs/outputs of tasks: documents, datasets, artifacts,
    code snippets, and other digital assets (R in the POSG state).

    Example:
        ```python
        Resource(
            name="Stakeholder Brief v1",
            description="Two-page summary for exec review",
            content="...",
            content_type="text/markdown",
        )
        ```
    """

    id: UUID = Field(default_factory=uuid4, description="Unique identifier for the resource")
    name: str = Field(
        ..., description="Human-readable resource name", examples=["Stakeholder Brief v1"]
    )
    description: str = Field(..., description="What this resource contains and how it is used")
    content: str | None = Field(
        default=None,
        description="Inline content for small artifacts. Large files should be stored externally and referenced here.",
    )
    content_type: str = Field(
        default="text/plain",
        description="MIME type, e.g., text/plain, text/markdown, application/json",
        examples=["text/markdown", "application/json"],
    )

    @property
    def resource_id(self) -> UUID:
        """Alias for id field to maintain compatibility."""
        return self.id

    def pretty_print(self, max_preview_chars: int = 5000) -> str:
        """Return a human-readable summary of the resource with a safe content preview."""
        lines: list[str] = []
        lines.append(f"Resource: {self.name} (ID: {self.id}, type={self.content_type})")
        if self.description:
            lines.append(f"  Description: {self.description}")
        if self.content:
            try:
                word_count = len(self.content.split())
            except Exception:
                word_count = 0
            char_len = len(self.content)
            lines.append(f"  Content stats: words={word_count}, chars={char_len}")
            preview = self.content[:max_preview_chars]
            if len(self.content) > max_preview_chars:
                preview += "... (truncated)"
            lines.append("  Content preview:")
            for line in preview.splitlines()[:60]:
                lines.append(f"    {line}")
        else:
            lines.append("  Content: <empty>")
        return "\n".join(lines)


class Task(BaseModel):
    """
    A task in the workflow system.

    Tasks represent atomic units of work that can be assigned to agents.
    They form nodes in the task dependency graph (G in the POSG state).
    """

    id: UUID = Field(default_factory=uuid4, description="Unique identifier for the task")
    name: str = Field(
        ..., description="Clear, descriptive task name", examples=["Draft technical memo"]
    )
    description: str = Field(
        ...,
        description="Detailed task description and objectives",
        examples=["Write a 2-page memo for execs."],
    )
    subtasks: list["Task"] = Field(
        default_factory=list, description="Subtasks that make up this task (recursive structure)"
    )
    parent_task_id: UUID | None = Field(
        default=None, description="ID of parent task if this is a subtask"
    )
    input_resource_ids: list[UUID] = Field(
        default_factory=list, description="IDs of required input resources"
    )
    output_resource_ids: list[UUID] = Field(
        default_factory=list, description="IDs of produced output resources"
    )
    dependency_task_ids: list[UUID] = Field(
        default_factory=list, description="Tasks that must complete before this one"
    )
    status: TaskStatus = Field(
        default=TaskStatus.PENDING, description="Execution status of the task"
    )
    assigned_agent_id: str | None = Field(
        default=None, description="ID of the agent currently assigned to this task"
    )
    execution_notes: list[str] = Field(
        default_factory=list, description="Free-form execution notes and manager instructions"
    )
    estimated_duration_hours: float | None = Field(
        default=None, description="Estimated duration in hours"
    )
    actual_duration_hours: float | None = Field(
        default=None, description="Actual duration in hours (reported by agent)"
    )
    estimated_cost: float | None = Field(
        default=None, description="Estimated cost in currency units"
    )
    actual_cost: float | None = Field(
        default=None, description="Actual cost in currency units (reported by agent)"
    )
    quality_score: float | None = Field(default=None, description="Quality assessment [0,1]")
    started_at: datetime | None = Field(default=None)
    completed_at: datetime | None = Field(default=None)
    deps_ready_at: datetime | None = Field(
        default=None, description="When all dependencies became satisfied"
    )
    effective_status: str | None = Field(
        default=None,
        description="Derived status for composites based on descendant leaves; for leaves equals status.",
    )

    @property
    def task_id(self) -> UUID:
        """Alias for id field to maintain compatibility."""
        return self.id

    def is_ready_to_start(self, completed_task_ids: set[UUID]) -> bool:
        """Check if all dependencies are satisfied."""
        return all((dep_id in completed_task_ids for dep_id in self.dependency_task_ids))

    def is_composite_task(self) -> bool:
        """Check if this task has subtasks (composite task)."""
        return len(self.subtasks) > 0

    def calculate_coordination_deadtime_seconds(self) -> float:
        """
        Calculate coordination deadtime for this task in seconds.

        Deadtime = max(0, start_time - deps_ready_time)
        Returns 0.0 if timestamps are not available.

        Returns:
            Coordination deadtime in seconds
        """
        if self.started_at is None or self.deps_ready_at is None:
            return 0.0
        deadtime_seconds = (self.started_at - self.deps_ready_at).total_seconds()
        return max(0.0, deadtime_seconds)

    def is_atomic_task(self) -> bool:
        """Check if this task has no subtasks (atomic task)."""
        return len(self.subtasks) == 0

    def get_all_subtasks_flat(self) -> list["Task"]:
        """Get all subtasks in a flat list (recursive)."""
        all_subtasks = []
        for subtask in self.subtasks:
            all_subtasks.append(subtask)
            all_subtasks.extend(subtask.get_all_subtasks_flat())
        return all_subtasks

    def get_atomic_subtasks(self) -> list["Task"]:
        """Get only the atomic (leaf) subtasks."""
        atomic_tasks = []
        for subtask in self.subtasks:
            if subtask.is_atomic_task():
                atomic_tasks.append(subtask)
            else:
                atomic_tasks.extend(subtask.get_atomic_subtasks())
        return atomic_tasks

    def add_subtask(self, subtask: "Task") -> None:
        """Add a subtask and set its parent reference."""
        subtask.parent_task_id = self.id
        self.subtasks.append(subtask)

    def remove_subtask(self, subtask_id: UUID) -> bool:
        """Remove a subtask by ID. Returns True if found and removed."""
        for i, subtask in enumerate(self.subtasks):
            if subtask.id == subtask_id:
                self.subtasks.pop(i)
                return True
            if subtask.remove_subtask(subtask_id):
                return True
        return False

    def find_task_by_id(self, task_id: UUID) -> "Task | None":
        """Find a task by ID in this task tree."""
        if self.id == task_id:
            return self
        for subtask in self.subtasks:
            found = subtask.find_task_by_id(task_id)
            if found:
                return found
        return None

    def sync_embedded_tasks_with_registry(self, task_registry: dict[UUID, "Task"]) -> None:
        """
        Synchronize embedded subtasks with the authoritative task registry.

        This fixes the bug where embedded subtasks become stale when the registry is updated.
        Recursively updates all embedded subtasks to match their registry counterparts.

        Args:
            task_registry: Dictionary mapping task IDs to authoritative Task objects
        """
        for i, subtask in enumerate(self.subtasks):
            if subtask.id in task_registry:
                registry_task = task_registry[subtask.id]
                self.subtasks[i] = registry_task
                registry_task.sync_embedded_tasks_with_registry(task_registry)
            else:
                subtask.sync_embedded_tasks_with_registry(task_registry)

    def pretty_print(self, indent: int = 0) -> str:
        """Return a human-readable summary of the task and selected fields."""
        prefix = "  " * indent
        lines: list[str] = []
        lines.append(f"{prefix}• Task: {self.name} (ID: {self.id})")
        lines.append(f"{prefix}  Status: {self.status.value}")
        if self.description:
            lines.append(f"{prefix}  Description: {self.description}")
        if self.estimated_duration_hours is not None:
            lines.append(f"{prefix}  Estimated hours: {self.estimated_duration_hours:.2f}")
        if self.actual_duration_hours is not None:
            lines.append(f"{prefix}  Actual hours: {self.actual_duration_hours:.2f}")
        if self.estimated_cost is not None:
            lines.append(f"{prefix}  Estimated cost: ${float(self.estimated_cost):.2f}")
        if self.actual_cost is not None:
            lines.append(f"{prefix}  Actual cost: ${float(self.actual_cost):.2f}")
        if self.dependency_task_ids:
            dep_ids = ", ".join((str(d) for d in self.dependency_task_ids))
            lines.append(f"{prefix}  Depends on: {dep_ids}")
        if self.input_resource_ids:
            lines.append(f"{prefix}  Input resources: {[str(r) for r in self.input_resource_ids]}")
        if self.output_resource_ids:
            lines.append(
                f"{prefix}  Output resources: {[str(r) for r in self.output_resource_ids]}"
            )
        if self.subtasks:
            lines.append(f"{prefix}  Subtasks:")
            for st in self.subtasks:
                lines.append(st.pretty_print(indent + 2))
        return "\n".join(lines)


class SubtaskData(BaseModel):
    """Structured data for a single subtask."""

    name: str = Field(..., description="Clear, descriptive name for the subtask")
    executive_summary: str = Field(
        ..., description="1-2 sentence summary of the purpose and significance of this subtask"
    )
    implementation_plan: str = Field(
        ..., description="Detailed steps and approach for completing this subtask"
    )
    acceptance_criteria: str = Field(
        ..., description="Specific, measurable criteria to verify task completion"
    )


class RunCondition(str, Enum):
    EACH_TIMESTEP = "each_timestep"
    ON_COMPLETION = "on_completion"
    BOTH = "both"


class AdditionalContextItem(str, Enum):
    """Declarative context signals a rubric can request for evaluation."""

    MANAGER_ACTIONS = "manager_actions"
    COMMS_BY_SENDER = "communications_by_sender"
    COMMS_BY_THREAD = "communications_by_thread"
    PREFERENCE_HISTORY = "preference_history"
    STAKEHOLDER_PROFILE = "stakeholder_profile"
    RESOURCES_BY_TASK = "resources_by_task"
    AGENT_TOOL_USAGE_BY_TASK = "agent_tool_usage_by_task"
    AGENT_PUBLIC_STATES = "agent_public_states"


class WorkflowRubric(BaseModel):
    """
    Workflow-level rubric that evaluates a workflow using either a Python function
    or an LLM prompt. Exactly one evaluation source must be provided.
    """

    name: str = Field(..., description="Name of the rubric")
    description: str | None = Field(
        default=None, description="Description of what this rubric measures"
    )
    max_score: float = Field(1.0, gt=0.0, description="Maximum possible score")
    evaluator_function: Callable[..., Any] | None = Field(
        default=None,
        description="Python function taking a workflow and returning either a numeric score, a (score, reasoning) tuple, an EvaluatedScore-like object with 'score' and 'reasoning', or any custom type (captured as raw_output).",
    )
    llm_prompt: str | None = Field(
        default=None, description="LLM prompt to use for evaluation (0..max_score output)"
    )
    llm_model: str = Field(
        default="o3", description="LLM model name to use if llm_prompt is provided"
    )
    run_condition: RunCondition = Field(
        default=RunCondition.EACH_TIMESTEP, description="When this rubric should be evaluated"
    )
    required_context: Set[AdditionalContextItem] = Field(
        default_factory=set,
        description="Optional set of context items this rubric needs at evaluation time",
    )

    @model_validator(mode="after")
    def check_evaluator_source(self) -> "WorkflowRubric":
        if self.evaluator_function is None and self.llm_prompt is None:
            raise ValueError("Must provide either evaluator_function or llm_prompt")
        if self.evaluator_function is not None and self.llm_prompt is not None:
            raise ValueError("Provide either evaluator_function OR llm_prompt, not both")
        return self


class AggregationStrategy(str, Enum):
    WEIGHTED_AVERAGE = "weighted_average"
    MIN = "min"
    MAX = "max"
    PRODUCT = "product"
    HARMONIC_MEAN = "harmonic_mean"


class Evaluator(BaseModel):
    """Container for a set of rubrics and an aggregation policy.

    This replaces the previous pattern where `Preference` directly embedded rubrics
    and an aggregation strategy. Use this wherever you want to evaluate a quantity
    (standalone) or wrap it inside a `Preference` for weighted aggregation.
    """

    name: str = Field(..., description="Evaluator name")
    description: str | None = Field(default=None, description="Optional human-readable description")
    aggregation: AggregationStrategy | Callable[..., float] = Field(
        default=AggregationStrategy.WEIGHTED_AVERAGE,
        description="Strategy to aggregate rubric scores. Is a simple strategy, or a callable if you want to use a custom aggregation function (eg: mean if something is True else zero).",
    )
    rubrics: list[WorkflowRubric] = Field(
        default_factory=list, description="List of rubrics this evaluator will run"
    )


class Constraint(BaseModel):
    """
    A regulatory or organizational constraint on workflow execution.

    Supports governance and compliance requirements.
    """

    constraint_id: UUID = Field(default_factory=uuid4)
    name: str = Field(..., description="Name of the constraint")
    description: str = Field(..., description="Detailed description of the constraint")
    constraint_type: str = Field(
        ..., description="Type: 'hard', 'soft', 'regulatory', 'organizational'"
    )
    enforcement_level: float = Field(ge=0.0, le=1.0, description="How strictly to enforce [0,1]")
    applicable_task_types: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class Preference(BaseModel):
    """
    A single preference dimension with its weight and associated evaluator.
    """

    name: str = Field(..., description="Name of the preference dimension")
    weight: float = Field(ge=0.0, le=1.0, description="Weight/importance of this preference [0,1]")
    description: str | None = Field(
        default=None, description="Optional description of what this preference measures"
    )
    evaluator: Evaluator | None = Field(
        default=None, description="Evaluator defining rubrics and aggregation for this preference"
    )

    def get_rubric_names(self) -> List[str]:
        """Get names of all rubrics in this preference's evaluator."""
        if self.evaluator is None:
            return []
        return [rubric.name for rubric in self.evaluator.rubrics]


class PreferenceWeights(BaseModel):
    """
    A collection of multi-objective preference weights for workflow optimization.
    Weights are automatically normalized to sum to 1.0 upon initialization.
    """

    preferences: List[Preference] = Field(
        default_factory=list, description="List of preference dimensions"
    )
    timestep: int = Field(default=0, description="Timestep at which these preferences apply")

    @model_validator(mode="after")
    def normalize_weights(self) -> "PreferenceWeights":
        total_weight = sum((p.weight for p in self.preferences))
        if total_weight > 0:
            for p in self.preferences:
                p.weight = p.weight / total_weight
        elif self.preferences:
            equal_weight = 1.0 / len(self.preferences)
            for p in self.preferences:
                p.weight = equal_weight
        return self

    def get_preference_names(self) -> List[str]:
        """Get all preference dimension names."""
        return [pref.name for pref in self.preferences]

    def get_preference_dict(self) -> dict[str, float]:
        """Get preferences as a dictionary mapping name to normalized weight."""
        return {pref.name: pref.weight for pref in self.preferences}

    def normalize(self) -> "PreferenceWeights":
        """Return a new PreferenceWeights with normalized weights."""
        return PreferenceWeights(preferences=[p.model_copy() for p in self.preferences])

    def get_preference_summary(self) -> str:
        """Get a summary of the preferences."""
        return "\n".join([f"{pref.name}: {pref.weight}" for pref in self.preferences])


class PreferenceChange(BaseModel):
    """
    Minimal event representing a change of preferences at a specific timestep.
    """

    timestep: int = Field(..., ge=0, description="Timestep at which the change occurs")
    preferences: PreferenceWeights = Field(
        ..., description="The full set of preferences active after the change"
    )
    change_type: str | None = Field(default=None, description="Type of change event")
    magnitude: float | None = Field(default=None, description="Magnitude of change if applicable")
    trigger_reason: str | None = Field(default=None, description="Reason the change was triggered")
    previous_weights: dict[str, float] | None = Field(
        default=None, description="Previous normalized weights by preference name"
    )
    new_weights: dict[str, float] | None = Field(
        default=None, description="New normalized weights by preference name"
    )


WeightUpdateMode = Literal["delta", "multiplier", "absolute"]

MissingPreferencePolicy = Literal["error", "ignore", "create_zero"]

RedistributionStrategy = Literal["proportional", "uniform"]


class PreferenceWeightUpdateRequest(BaseModel):
    """
    Request to update a stakeholder's preference weights at a given timestep.

    - mode="delta": add deltas to existing weights for the specified names
    - mode="multiplier": multiply existing weights by given factors
    - mode="absolute": set specified names to exact weights; optionally
      redistribute the remainder across unspecified names
    """

    timestep: int = Field(..., ge=0, description="Timestep when the update applies")
    changes: dict[str, float] = Field(
        default_factory=dict,
        description="Mapping from preference name to change value (delta/factor/absolute)",
    )
    mode: WeightUpdateMode = Field(default="delta")
    normalize: bool = Field(default=True, description="Normalize resulting weights to sum to 1.0")
    clamp_zero: bool = Field(
        default=True, description="Clamp any negative weights to zero after update"
    )
    missing: MissingPreferencePolicy = Field(
        default="error", description="Policy for unknown preference names in 'changes'"
    )
    redistribution: RedistributionStrategy = Field(
        default="proportional",
        description="Redistribution strategy for unspecified names when mode='absolute'",
    )


class AgentConfig(BaseModel):
    """Base configuration for an agent instance."""

    agent_id: str = Field(..., description="Unique identifier for the agent")
    agent_type: str = Field(..., description="Type of agent (ai, human_mock)")
    system_prompt: str = Field(..., description="System instructions for the agent")
    model_name: str = Field(default="gpt-4.1", description="LLM model to use")
    agent_description: str = Field(..., description="Description of the agent")
    agent_capabilities: list[str] = Field(..., description="Capabilities of the agent")

    def get_agent_capability_summary(self) -> str:
        """Print a summary of the agent's configuration."""
        return f"Agent {self.agent_id} [{self.agent_type}] | Description: {self.agent_description} | Capabilities: {self.agent_capabilities}"

    @field_validator("agent_id")
    @classmethod
    def validate_agent_id(cls, v: str) -> str:
        """Validate agent_id is not empty and follows naming conventions."""
        if not v or not v.strip():
            raise ValueError("agent_id cannot be empty")
        return v.strip()

    @field_validator("system_prompt")
    @classmethod
    def validate_system_prompt(cls, v: str) -> str:
        """Validate system_prompt is not empty."""
        if not v or not v.strip():
            raise ValueError("system_prompt cannot be empty")
        if len(v) < 10:
            raise ValueError("system_prompt must be at least 10 characters")
        return v.strip()


class AIAgentConfig(AgentConfig):
    """Configuration specific to AI agents."""

    agent_type: str = Field(default="ai", description="Type of agent")


class HumanAgentConfig(AgentConfig):
    """Unified configuration for human mock agents - includes both technical and persona aspects."""

    agent_type: str = Field(default="human_mock", description="Type of agent")
    name: str = Field(..., description="Human worker name")
    role: str = Field(..., description="Job title/role")
    experience_years: int = Field(..., ge=0, description="Years of experience")
    expertise_areas: list[str] = Field(default_factory=list, description="Areas of expertise")
    personality_traits: list[str] = Field(
        default_factory=list, description="Personality characteristics"
    )
    work_style: str = Field(
        default="methodical", description="Working style (methodical, creative, fast, etc.)"
    )
    background: str = Field(..., description="Professional background and context")
    base_work_hours: float = Field(
        default=8.0, ge=1.0, le=16.0, description="Daily work hours for this human"
    )
    hourly_rate: float = Field(default=50.0, description="Hourly rate for cost calculation")
    interruption_tolerance: float = Field(
        default=0.7, ge=0.0, le=1.0, description="How well this human handles interruptions"
    )
    base_quality_mean: float = Field(
        default=0.85, ge=0.0, le=1.0, description="Base quality level [0-1]"
    )
    fatigue_rate: float = Field(
        default=0.02, ge=0.0, description="Quality degradation per hour worked"
    )
    misunderstanding_rate: float = Field(
        default=0.05, ge=0.0, le=1.0, description="Chance of task misunderstanding"
    )

    @property
    def experience_factor(self) -> float:
        """Auto-calculate experience factor from years."""
        return min(0.5 + self.experience_years * 0.1, 3.0)

    @field_validator("hourly_rate")
    @classmethod
    def validate_hourly_rate(cls, v: float) -> float:
        """Validate hourly_rate is positive."""
        if v <= 0:
            raise ValueError("hourly_rate must be positive")
        return v

    def generate_roleplay_prompt(self) -> str:
        """Generate a roleplay prompt for the AI to embody this persona."""
        expertise_str = (
            ", ".join(self.expertise_areas) if self.expertise_areas else "general business"
        )
        traits_str = (
            ", ".join(self.personality_traits) if self.personality_traits else "professional"
        )
        return PERSONA_ROLEPLAY_TEMPLATE.format(
            name=self.name,
            role=self.role,
            experience_years=self.experience_years,
            background=self.background,
            expertise=expertise_str,
            personality=traits_str,
            work_style=self.work_style,
        )


class StakeholderPublicProfile(BaseModel):
    """Minimal public information about the stakeholder available to the manager."""

    display_name: str = Field(..., description="Stakeholder display name")
    role: str = Field(..., description="Stakeholder role/title")
    preference_summary: str = Field(
        default="", description="High-level description of stakeholder priorities."
    )


class StakeholderConfig(AgentConfig):
    """Configuration for the stakeholder agent persona and messaging behavior.

    Inherits from AgentConfig to align with AgentInterface typing and provide
    standard fields like model_name and system_prompt.
    """

    agent_type: str = Field(default="stakeholder", description="Type identifier")
    name: str = Field(..., description="Stakeholder name")
    role: str = Field(..., description="Stakeholder role/title")
    persona_description: str = Field(
        default="Stakeholder persona", description="Short persona description for messaging style"
    )
    model_name: str = Field(description="Model name to use for stakeholder agent", default="o3")
    initial_preferences: PreferenceWeights = Field(
        description="Initial, normalized preference weights owned by the stakeholder"
    )
    response_latency_steps_min: int = Field(
        default=0, ge=0, description="Minimum reply latency in timesteps"
    )
    response_latency_steps_max: int = Field(
        default=2, ge=0, description="Maximum reply latency in timesteps"
    )
    push_probability_per_timestep: float = Field(
        default=0.0, ge=0.0, le=1.0, description="Chance to proactively push a suggestion"
    )
    suggestion_rate: float = Field(
        default=0.25, ge=0.0, le=1.0, description="How often suggestions are created when pushing"
    )
    clarification_reply_rate: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Probability of replying to a clarification message",
    )
    strictness: float = Field(
        default=0.5, ge=0.0, le=1.0, description="Higher is stricter when reviewing work"
    )
    verbosity: int = Field(
        default=1, ge=0, le=5, description="Verbosity of stakeholder messages (affects comm cost)"
    )


class StakeholderPreferenceState(BaseModel):
    """Stakeholder-owned preference state for a given timestep."""

    weights: PreferenceWeights = Field(..., description="Preference weights")
    timestep: int = Field(..., description="Timestep for which weights apply")
    change_event: PreferenceChange | None = Field(
        default=None, description="Optional change event metadata"
    )


AgentInterface = AgentConfig


class MessageType(str, Enum):
    """Types of messages that can be sent between agents."""

    DIRECT = "direct"
    BROADCAST = "broadcast"
    REQUEST = "request"
    RESPONSE = "response"
    ALERT = "alert"
    STATUS_UPDATE = "status_update"
    GENERAL = "general"


class Message(BaseModel):
    """
    A communication message in the system.

    Messages form part of the communication history (C in the POSG state).
    Enhanced with thread support, multiple recipients, and read tracking.
    """

    message_id: UUID = Field(default_factory=uuid4, description="Unique message ID")
    sender_id: str = Field(..., description="ID of the sender (agent or manager)")
    receiver_id: str | None = Field(
        default=None, description="Primary receiver ID, None for broadcast"
    )
    recipients: list[str] = Field(
        default_factory=list, description="List of recipient agent IDs (for multi-cast messages)"
    )
    content: str = Field(
        ...,
        description="Message content body (avoid PII in shared environments)",
        examples=["Kickoff in 5 minutes"],
    )
    message_type: MessageType = Field(
        default=MessageType.GENERAL, description="Type of message for categorization and filtering"
    )
    timestamp: datetime = Field(default_factory=datetime.now, description="Send time")
    thread_id: UUID | None = Field(default=None, description="Thread this message belongs to")
    parent_message_id: UUID | None = Field(default=None, description="Message this is replying to")
    related_task_id: UUID | None = Field(
        default=None, description="Task this message is related to"
    )
    priority: int = Field(default=1, ge=1, le=5, description="Message priority (1=low, 5=critical)")
    read_by: dict[str, datetime] = Field(
        default_factory=dict, description="Tracking of when each recipient read the message"
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict, description="Additional metadata for the message"
    )

    @field_validator("content")
    @classmethod
    def validate_content(cls, v: str) -> str:
        """Validate message content is not empty."""
        if not v or not v.strip():
            raise ValueError("Message content cannot be empty")
        return v.strip()

    @field_validator("recipients")
    @classmethod
    def validate_recipients(cls, v: list[str]) -> list[str]:
        """Ensure recipient list has unique values."""
        return list(set(v)) if v else []

    def mark_read_by(self, agent_id: str) -> None:
        """Mark this message as read by an agent."""
        self.read_by[agent_id] = datetime.now()

    def is_broadcast(self) -> bool:
        """Check if this is a broadcast message."""
        return self.message_type == MessageType.BROADCAST or self.receiver_id is None

    def get_all_recipients(self) -> set[str]:
        """Get all recipients including primary receiver."""
        recipients = set(self.recipients)
        if self.receiver_id:
            recipients.add(self.receiver_id)
        return recipients


class MessageGrouping(str, Enum):
    """Grouping options for message views."""

    BY_SENDER = "sender"
    BY_THREAD = "thread"


class SenderMessagesView(BaseModel):
    """Messages grouped by the sending agent."""

    sender_id: str
    total_messages: int
    most_recent_at: datetime
    messages: list[Message]


class ThreadMessagesView(BaseModel):
    """Messages grouped by thread."""

    thread_id: UUID | None
    topic: str | None = None
    participants: list[str] = Field(default_factory=list)
    related_task_id: UUID | None = None
    total_messages: int
    last_activity: datetime
    messages: list[Message]


class Workflow(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    "\n    A complete workflow containing tasks, agents, and execution state.\n\n    This represents the core environment for the Manager Agent POSG.\n    "
    id: UUID = Field(
        default_factory=uuid4,
        description="Unique identifier for this workflow instance.",
        examples=[str(uuid4())],
    )
    name: str = Field(
        ..., description="Human-readable name for dashboards and logs.", examples=["IPO Readiness"]
    )
    workflow_goal: str = Field(
        ...,
        description="Detailed objective and acceptance criteria for the workflow run.",
        examples=[
            "Objective: Secure AOC and Operating Licence. Acceptance: AOC issued, OL granted, inspections passed."
        ],
    )
    owner_id: UUID = Field(
        ..., description="ID of the workflow owner (tenant/user)", examples=[str(uuid4())]
    )
    tasks: dict[UUID, Task] = Field(
        default_factory=dict,
        description="Task graph nodes (G). Keys are task UUIDs; values are Task models.",
        examples=[{str(uuid4()): Task(name="Draft plan", description="...").model_dump()}],
    )
    resources: dict[UUID, Resource] = Field(
        default_factory=dict,
        description="Resource registry (R). Keys are resource UUIDs; values are Resource models.",
    )
    agents: dict[str, AgentInterface] = Field(
        default_factory=dict,
        description="Available agents (W). Keys are agent ids; values are live AgentInterface instances.",
    )
    messages: list[Message] = Field(
        default_factory=list,
        description="Communication history (C). Appended by the communication service.",
    )
    constraints: list[Constraint] = Field(
        default_factory=list, description="Hard/soft constraints used by evaluators and planning"
    )
    started_at: datetime | None = Field(
        default=None, description="When execution started (set by engine)"
    )
    seed: int = Field(default=42, description="Run-level seed for reproducibility")
    completed_at: datetime | None = Field(
        default=None, description="When execution completed (set by engine)"
    )
    is_active: bool = Field(default=False, description="Whether the workflow is currently active")
    total_cost: float = Field(default=0.0, description="Cumulative actual cost reported by agents")
    total_simulated_hours: float = Field(
        default=0.0, description="Total simulated time across all completed tasks (hours)"
    )

    @property
    def workflow_id(self) -> UUID:
        """Alias for id field to maintain compatibility."""
        return self.id

    @property
    def total_budget(self) -> float:
        """Sum of estimated costs across all tasks and nested subtasks."""
        total = 0.0
        for task in self.tasks.values():
            if task.estimated_cost is not None:
                try:
                    total += float(task.estimated_cost)
                except Exception:
                    pass
            for subtask in task.get_all_subtasks_flat():
                if subtask.estimated_cost is not None:
                    total += float(subtask.estimated_cost)
        return total

    @property
    def total_expected_hours(self) -> float:
        """Sum of estimated duration hours across all tasks and nested subtasks."""
        total = 0.0
        for task in self.tasks.values():
            if task.estimated_duration_hours is not None:
                total += float(task.estimated_duration_hours)
            for subtask in task.get_all_subtasks_flat():
                if subtask.estimated_duration_hours is not None:
                    total += float(subtask.estimated_duration_hours)
        return total

    def add_task(self, task: Task) -> None:
        """Add a task to the workflow."""
        self.tasks[task.id] = task

    def add_resource(self, resource: Resource) -> None:
        """Add a resource to the workflow."""
        self.resources[resource.id] = resource

    def get_task_output_resources(self, task: Task) -> list[Resource]:
        """Return realized output resources for a given task by id lookup."""
        results: list[Resource] = []
        for rid in task.output_resource_ids:
            res = self.resources.get(rid)
            if isinstance(res, Resource):
                results.append(res)
        return results

    def get_all_resources(self) -> list[Resource]:
        """Return all resources currently registered in the workflow."""
        return list(self.resources.values())

    def add_agent(self, agent: AgentInterface) -> None:
        """Add an agent to the workflow."""
        self.agents[agent.agent_id] = agent

    def find_task_by_id(self, task_id: UUID) -> Task | None:
        """Find a task by ID in the workflow."""
        if task_id in self.tasks:
            return self.tasks[task_id]
        for task in self.tasks.values():
            found = task.find_task_by_id(task_id)
            if found:
                return found
        return None

    def is_complete(self) -> bool:
        """Check if all atomic tasks in the workflow are completed."""
        atomic_tasks = [task for task in self.tasks.values() if task.is_atomic_task()]
        if not atomic_tasks:
            return False
        return all((task.status == TaskStatus.COMPLETED for task in atomic_tasks))

    def get_task_dependencies_graph(self) -> dict[UUID, list[UUID]]:
        """Get the task dependency graph as adjacency list."""
        return {task_id: task.dependency_task_ids for task_id, task in self.tasks.items()}

    def pretty_print(self, include_resources: bool = True, max_preview_chars: int = 300) -> str:
        """Return a human-readable summary of the workflow, tasks, and selected resources."""
        lines: list[str] = []
        lines.append("-" * 70)
        lines.append(f"Workflow: {self.name} (ID: {self.id})")
        lines.append(f"Goal: {self.workflow_goal}")
        lines.append(
            f"Budget (est): ${self.total_budget:.2f} | Expected hours: {self.total_expected_hours:.2f}"
        )
        lines.append(f"Cost (actual): ${self.total_cost:.2f}")
        lines.append(
            f"Agents: {len(self.agents)} | Resources: {len(self.resources)} | Tasks: {len(self.tasks)}"
        )
        lines.append("-" * 70)
        lines.append("Tasks:")
        for t in self.tasks.values():
            lines.append(t.pretty_print(indent=1))
        if include_resources and self.resources:
            lines.append("\nResources:")
            for r in self.resources.values():
                try:
                    lines.append(r.pretty_print(max_preview_chars=max_preview_chars))
                except Exception:
                    lines.append(f"Resource: {r.name} (ID: {r.id})")
        return "\n".join(lines)


class AgentToolUseEvent(BaseModel):
    """Compact, privacy-aware record of a single tool invocation."""

    timestamp: datetime = Field(default_factory=datetime.now)
    agent_id: str = Field(..., description="ID of the invoking agent")
    task_id: UUID | None = Field(default=None, description="Task the tool call was associated with")
    tool_name: str = Field(..., description="Name of the tool invoked")
    succeeded: bool = Field(default=True, description="Whether the call succeeded")

    # Performance/usage metrics (optional, if available)
    duration_ms: int | None = Field(default=None)
    latency_ms: int | None = Field(default=None)
    tokens_in: int | None = Field(default=None)
    tokens_out: int | None = Field(default=None)
    result_size: int | None = Field(default=None, description="Approx size of result")
    external_calls: int | None = Field(default=None, description="Downstream calls")

    # Redacted parameters
    args_fingerprint: str | None = Field(
        default=None, description="Hash/shape of arguments; no raw content"
    )

    # Error reporting (if failed)
    error_type: str | None = Field(default=None)
    error_message: str | None = Field(default=None)

    # Provenance (if applicable)
    evidence_sources: list[str] | None = Field(
        default=None, description="List of domains/URLs referenced"
    )


class AgentPublicState(BaseModel):
    """Redacted public snapshot of an agent for evaluation purposes."""

    agent_id: str = Field(...)
    agent_type: str = Field(...)

    # Assignment and availability
    is_available: bool = Field(default=True)
    current_task_ids: list[UUID] = Field(default_factory=list)
    max_concurrent_tasks: int = Field(default=1)

    # Performance tracking
    tasks_completed: int = Field(default=0)
    joined_at: datetime = Field(default_factory=datetime.now)

    # Optional aggregates (if available)
    avg_tool_latency_ms: float | None = Field(default=None)
    avg_tokens_in: float | None = Field(default=None)
    avg_tokens_out: float | None = Field(default=None)
    avg_cost_per_task: float | None = Field(default=None)

    # Summaries (optional)
    tool_usage_summary: dict[str, int] | None = Field(
        default=None, description="Counts by tool name"
    )
    tool_error_rates: dict[str, float] | None = Field(
        default=None, description="Error rate per tool name (0..1)"
    )
    comms_summary: dict[str, Any] | None = Field(
        default=None, description="Communication behavior summary"
    )


class ValidationContext(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    workflow: Workflow
    current_preferences: PreferenceWeights | None = None
    timestep: int = 0
    manager_actions: list[Any] | None = None
    communications_by_sender: list[SenderMessagesView] | None = None
    communications_by_thread: list[ThreadMessagesView] | None = None
    preference_history: list[dict[str, Any]] | None = None
    stakeholder_profile: dict[str, Any] | None = None
    resources_by_task: dict[UUID, list[Resource]] | None = None
    all_resources: list[Resource] | None = None
    agent_tool_usage_by_task: dict[UUID, list[AgentToolUseEvent]] | None = None
    agent_public_states: dict[str, AgentPublicState] | None = None
