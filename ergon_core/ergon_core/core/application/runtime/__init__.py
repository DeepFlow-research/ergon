"""Runtime application owner for run graph and task lifecycle behavior."""

from importlib import import_module
from types import ModuleType

_ALIASES = {
    "execution": "task_execution",
    "inspection": "task_inspection",
    "management": "task_management",
    "propagation": "lifecycle",
    "runs": "run_records",
    "service": "run_lifecycle",
}

__all__ = [
    "execution",
    "inspection",
    "management",
    "propagation",
    "runs",
    "service",
]


def __getattr__(name: str) -> ModuleType:
    if name not in _ALIASES:
        raise AttributeError(name)
    module = import_module(f"{__name__}.{_ALIASES[name]}")
    globals()[name] = module
    return module
