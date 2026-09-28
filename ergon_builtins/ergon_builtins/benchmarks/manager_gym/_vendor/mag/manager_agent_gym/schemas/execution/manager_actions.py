"""Ergon shim for upstream ``manager_agent_gym.schemas.execution.manager_actions``.

Upstream actions execute themselves against its engine. Ergon executes manager
actions natively and records them as
``ergon_builtins.benchmarks.manager_gym.actions.ActionResult``, which keeps the
upstream fields. ``ValidationContext.manager_actions`` accepts those records
without re-validating them.
"""

from typing import Any

ActionResult = Any
