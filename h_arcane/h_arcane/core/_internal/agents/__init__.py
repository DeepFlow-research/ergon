"""Agents domain - agent interfaces and worker registry.

This domain handles:
- Agent interfaces (BaseStakeholder, BaseToolkit)
- AgentRegistry for collecting workers from task trees

Structure:
- base.py: Agent interfaces
- registry.py: AgentRegistry for worker collection and persistence

Note: Task execution is now handled by the DAG workflow system
(task_execute via execute_task()).
"""

from h_arcane.core._internal.agents.base import BaseStakeholder, BaseToolkit
from h_arcane.core._internal.agents.registry import AgentRegistry

__all__ = [
    # Interfaces
    "BaseStakeholder",
    "BaseToolkit",
    # Registry
    "AgentRegistry",
]
