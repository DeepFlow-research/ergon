"""Composed registry: merges sub-registries based on installed capabilities.

No decorators, no scanning.  Sub-registries use eager, fully-typed imports.
The only conditionality is at this composition boundary.
"""

from collections.abc import Callable

import structlog

from h_arcane.api import Benchmark, Evaluator, Worker
from h_arcane.core.providers.generation.model_resolution import (
    ResolvedModel,
    register_model_backend,
)
from h_arcane.core.providers.sandbox.manager import BaseSandboxManager

from arcane_builtins.registry_core import (
    BENCHMARKS as _core_benchmarks,
    EVALUATORS as _core_evaluators,
    MODEL_BACKENDS as _core_model_backends,
    SANDBOX_MANAGERS as _core_sandbox_managers,
    WORKERS as _core_workers,
)

log = structlog.get_logger()

# -- Start from core (always available) ------------------------------------

WORKERS: dict[str, type[Worker]] = {**_core_workers}
BENCHMARKS: dict[str, type[Benchmark]] = {**_core_benchmarks}
EVALUATORS: dict[str, type[Evaluator]] = {**_core_evaluators}
SANDBOX_MANAGERS: dict[str, type[BaseSandboxManager]] = {**_core_sandbox_managers}

_model_backends: dict[str, Callable[..., ResolvedModel]] = {**_core_model_backends}

# -- Capability: local-models ----------------------------------------------

try:
    from arcane_builtins.registry_local_models import (
        MODEL_BACKENDS as _local_model_backends,
    )

    _model_backends.update(_local_model_backends)
except ImportError:
    log.info(
        "arcane-builtins[local-models] not installed; local transformers inference unavailable"
    )

# -- Capability: data ------------------------------------------------------

try:
    from arcane_builtins.registry_data import (
        BENCHMARKS as _data_benchmarks,
        EVALUATORS as _data_evaluators,
    )

    BENCHMARKS.update(_data_benchmarks)
    EVALUATORS.update(_data_evaluators)
except ImportError:
    log.info(
        "arcane-builtins[data] not installed; gdpeval and researchrubrics benchmarks unavailable"
    )

# -- Register model backends -----------------------------------------------

for prefix, resolver in _model_backends.items():
    register_model_backend(prefix, resolver)

# -- Install hints for slugs that require optional capabilities -------------

INSTALL_HINTS: dict[str, str] = {
    "transformers": "pip install 'arcane-builtins[local-models]'",
    "gdpeval": "pip install 'arcane-builtins[data]'",
    "researchrubrics": "pip install 'arcane-builtins[data]'",
    "research-rubric": "pip install 'arcane-builtins[data]'",
}
