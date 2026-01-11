"""Agents domain - agent interfaces and task execution.

This domain handles:
- Agent interfaces (BaseStakeholder, BaseToolkit)
- Task execution workflow (worker_execute)

Structure:
- base.py: Agent interfaces
- inngest_functions.py: worker_execute
- events.py: ExecutionDoneEvent
"""

from h_arcane.core.agents.base import BaseStakeholder, BaseToolkit
from h_arcane.core.agents.events import ExecutionDoneEvent
from h_arcane.core.agents.inngest_functions import worker_execute

__all__ = [
    # Interfaces
    "BaseStakeholder",
    "BaseToolkit",
    # Inngest functions
    "worker_execute",
    # Events
    "ExecutionDoneEvent",
]
