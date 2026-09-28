"""Ergon shim for upstream ``manager_agent_gym.core.workflow_agents.interface``.

Upstream stores live agent objects in ``Workflow.agents``. Ergon runs each actor
as a native worker and stores only its configuration there, so the vendored
``Workflow`` model validates agents as ``AgentConfig`` instances.
"""

from ...schemas.workflow_agents.config import AgentConfig

AgentInterface = AgentConfig
