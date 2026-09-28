"""Ergon shim for upstream ``manager_agent_gym.core.workflow_agents.stakeholder_agent``.

Upstream's stakeholder agent calls a model to reply to the manager. In Ergon the
stakeholder runs as a native worker and ``Workflow.agents`` holds configurations,
so "constructing" a stakeholder agent returns its configuration unchanged.
"""

from ...schemas.workflow_agents.stakeholder import StakeholderConfig


def StakeholderAgent(config: StakeholderConfig) -> StakeholderConfig:  # noqa: N802
    """Return ``config``; Ergon has no live stakeholder agent object."""
    return config
