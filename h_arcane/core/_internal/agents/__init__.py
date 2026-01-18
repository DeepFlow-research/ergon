"""Agents domain - agent interfaces and task execution.

This domain handles:
- Agent interfaces (BaseStakeholder, BaseToolkit)
- Task execution workflow (worker_execute)
- AgentRegistry for collecting workers from task trees

Structure:
- base.py: Agent interfaces
- registry.py: AgentRegistry for worker collection and persistence
- inngest_functions.py: worker_execute
- events.py: ExecutionDoneEvent

Note: Import inngest_functions directly to avoid circular imports:
    from h_arcane.core._internal.agents.inngest_functions import worker_execute
"""

# Only export non-circular imports at module level
from h_arcane.core._internal.agents.base import BaseStakeholder, BaseToolkit
from h_arcane.core._internal.agents.events import ExecutionDoneEvent
from h_arcane.core._internal.agents.registry import AgentRegistry

__all__ = [
    # Interfaces
    "BaseStakeholder",
    "BaseToolkit",
    # Registry
    "AgentRegistry",
    # Events
    "ExecutionDoneEvent",
]
