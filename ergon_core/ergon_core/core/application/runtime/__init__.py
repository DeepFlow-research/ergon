"""Runtime application owner for sample graph and task lifecycle behavior."""

from importlib import import_module
from types import ModuleType

_ALIASES = {
    "execution": "task_execution",
    "inspection": "task_inspection",
    "management": "task_management",
    "propagation": "lifecycle",
    "samples": "sample_records",
    "service": "sample_lifecycle",
}

__all__ = [
    "execution",
    "inspection",
    "management",
    "propagation",
    "samples",
    "service",
]


def __getattr__(name: str) -> ModuleType:
    if name not in _ALIASES:
        raise AttributeError(name)
    module = import_module(f"{__name__}.{_ALIASES[name]}")
    globals()[name] = module
    return module
