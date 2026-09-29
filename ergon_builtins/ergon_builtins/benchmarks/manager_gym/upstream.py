"""The upstream Manager Agent Gym names that the native adapter builds on.

Everything here comes from the vendored copy of MAG in ``_vendor/mag`` (see its
README for provenance). Native modules import upstream types, scenario
factories, evaluators and prompts from this module only, so the boundary
between vendored and native code stays in one place.
"""

import json
from pathlib import Path

from ._vendor.mag.examples.common_stakeholders import (
    create_stakeholder_agent,
)
from ._vendor.mag.examples.scenarios import (
    SCENARIOS,
    ScenarioSpec,
)
from ._vendor.mag.manager_agent_gym.core.decomposition.prompts import (
    TASK_DECOMPOSITION_PROMPT,
)
from ._vendor.mag.manager_agent_gym.core.evaluation.common_evaluators import (
    build_default_evaluators,
)
from ._vendor.mag.manager_agent_gym.core.evaluation.scenario_constraints import (
    build_constraints_for_scenario,
)
from ._vendor.mag.manager_agent_gym.core.manager_agent.prompts.structured_manager_prompts import (
    STRUCTURED_MANAGER_SYSTEM_PROMPT_TEMPLATE,
)
from ._vendor.mag.manager_agent_gym.core.workflow_agents.prompts.ai_agent_prompts import (
    AI_AGENT_TASK_TEMPLATE,
    NO_RESOURCES_MESSAGE,
)
from ._vendor.mag.manager_agent_gym.core.workflow_agents.prompts.human_agent_prompts import (
    HUMAN_SIMULATION_INSTRUCTIONS_TEMPLATE,
    HUMAN_TASK_ASSIGNMENT_TEMPLATE,
)
from ._vendor.mag.manager_agent_gym.schemas.core.base import (
    TaskStatus,
)
from ._vendor.mag.manager_agent_gym.schemas.core.communication import (
    Message,
    MessageType,
    SenderMessagesView,
    ThreadMessagesView,
)
from ._vendor.mag.manager_agent_gym.schemas.core.resources import (
    Resource,
)
from ._vendor.mag.manager_agent_gym.schemas.core.tasks import (
    Task,
)
from ._vendor.mag.manager_agent_gym.schemas.core.workflow import (
    Workflow,
)
from ._vendor.mag.manager_agent_gym.schemas.evaluation.success_criteria import (
    ValidationContext,
)
from ._vendor.mag.manager_agent_gym.schemas.preferences.evaluator import Evaluator
from ._vendor.mag.manager_agent_gym.schemas.preferences.preference import (
    Preference,
    PreferenceWeights,
)
from ._vendor.mag.manager_agent_gym.schemas.preferences.rubric import (
    AdditionalContextItem,
    RunCondition,
    WorkflowRubric,
)
from ._vendor.mag.manager_agent_gym.schemas.preferences.weight_update import (
    PreferenceWeightUpdateRequest,
)
from ._vendor.mag.manager_agent_gym.schemas.workflow_agents.config import (
    AgentConfig,
    AIAgentConfig,
    HumanAgentConfig,
)
from ._vendor.mag.manager_agent_gym.schemas.workflow_agents.stakeholder import (
    StakeholderConfig,
)
from ._vendor.mag.manager_agent_gym.schemas.workflow_agents.telemetry import (
    AgentPublicState,
    AgentToolUseEvent,
)

_MANIFEST = Path(__file__).parent / "_vendor" / "mag" / "MANIFEST.json"
UPSTREAM_REVISION: str = json.loads(_MANIFEST.read_text())["revision"]
"""The upstream MAG commit the vendored sources were copied from."""

__all__ = [
    "UPSTREAM_REVISION",
    "AI_AGENT_TASK_TEMPLATE",
    "HUMAN_SIMULATION_INSTRUCTIONS_TEMPLATE",
    "HUMAN_TASK_ASSIGNMENT_TEMPLATE",
    "NO_RESOURCES_MESSAGE",
    "SCENARIOS",
    "STRUCTURED_MANAGER_SYSTEM_PROMPT_TEMPLATE",
    "TASK_DECOMPOSITION_PROMPT",
    "AIAgentConfig",
    "AdditionalContextItem",
    "AgentConfig",
    "AgentPublicState",
    "AgentToolUseEvent",
    "Evaluator",
    "HumanAgentConfig",
    "Message",
    "MessageType",
    "Preference",
    "PreferenceWeightUpdateRequest",
    "PreferenceWeights",
    "Resource",
    "RunCondition",
    "ScenarioSpec",
    "SenderMessagesView",
    "StakeholderConfig",
    "Task",
    "TaskStatus",
    "ThreadMessagesView",
    "ValidationContext",
    "Workflow",
    "WorkflowRubric",
    "build_constraints_for_scenario",
    "build_default_evaluators",
    "create_stakeholder_agent",
]
