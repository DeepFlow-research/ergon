"""Central registry for all Inngest functions.

This module aggregates Inngest functions from across domains,
providing a single import point for api/main.py.

Convention:
- Each domain with Inngest functions has an `inngest_functions.py` module
- Each domain has an `events.py` module for input/output schemas (contracts)
- Domain logic (base.py, schemas.py, rules/) stays separate from Inngest wiring
"""

from typing import Any

from inngest import Function

from h_arcane.core.agents.inngest_functions import worker_execute
from h_arcane.core.evaluation.inngest_functions import (
    evaluate_criterion_fn,
    evaluate_task_run,
    run_evaluate,
)
from h_arcane.core.infrastructure.inngest_functions import run_cleanup

# All Inngest functions for registration with FastAPI/Inngest
ALL_FUNCTIONS: list[Function[Any]] = [
    # Agents - task execution
    worker_execute,
    # Evaluation - scoring and judging
    run_evaluate,
    evaluate_task_run,
    evaluate_criterion_fn,
    # Infrastructure - cleanup
    run_cleanup,
]

__all__ = [
    "ALL_FUNCTIONS",
    # Agents
    "worker_execute",
    # Evaluation
    "run_evaluate",
    "evaluate_task_run",
    "evaluate_criterion_fn",
    # Infrastructure
    "run_cleanup",
]
