"""Register built-in Ergon components into the core public registry.

No decorators, no scanning. Sub-registries use eager, fully typed imports.
The only conditionality is at this composition boundary.
"""

from collections.abc import Callable

import structlog
from ergon_core.api import Benchmark, Worker
from ergon_core.api.registry import ComponentRegistry, registry
from ergon_core.api.rubric import Evaluator
from ergon_core.core.infrastructure.sandbox.manager import BaseSandboxManager

from ergon_builtins.models.resolution import (
    ResolvedModel,
)
from ergon_builtins.registry_core import (
    BENCHMARKS as _core_benchmarks,
)
from ergon_builtins.registry_core import (
    EVALUATORS as _core_evaluators,
)
from ergon_builtins.registry_core import (
    MODEL_BACKENDS as _core_model_backends,
)
from ergon_builtins.registry_core import (
    SANDBOX_MANAGERS as _core_sandbox_managers,
)
from ergon_builtins.registry_core import (
    SANDBOX_TEMPLATES,
)
from ergon_builtins.registry_core import (
    WORKERS as _core_workers,
)
from ergon_builtins.registry_core import register_core_builtins

log = structlog.get_logger()

# -- Explicit registration --------------------------------------------------


def register_builtins(target: ComponentRegistry = registry) -> None:
    """Register builtins available in the current environment."""

    register_core_builtins(target)
    _register_local_model_builtins()
    _register_data_builtins(target)


def _register_local_model_builtins() -> None:
    try:
        from ergon_builtins.registry_local_models import register_local_model_builtins
    except ImportError:
        log.info("ergon-builtins[local-models] not installed; local transformers inference unavailable")
        return

    register_local_model_builtins()


def _register_data_builtins(target: ComponentRegistry) -> None:
    try:
        from ergon_builtins.registry_data import register_data_builtins
    except ImportError:
        log.info(
            "ergon-builtins[data] not installed; gdpeval and researchrubrics benchmarks unavailable"
        )
        return

    register_data_builtins(target)


# -- Backwards-compatible snapshots ----------------------------------------

WORKERS: dict[str, Callable[..., Worker]] = {**_core_workers}
BENCHMARKS: dict[str, type[Benchmark]] = {**_core_benchmarks}
EVALUATORS: dict[str, type[Evaluator]] = {**_core_evaluators}
SANDBOX_MANAGERS: dict[str, type[BaseSandboxManager]] = {**_core_sandbox_managers}

_model_backends: dict[str, Callable[..., ResolvedModel]] = {**_core_model_backends}

# -- Capability: local-models ----------------------------------------------

try:
    from ergon_builtins.registry_local_models import (
        MODEL_BACKENDS as _local_model_backends,
    )

    _model_backends.update(_local_model_backends)
except ImportError:
    log.info("ergon-builtins[local-models] not installed; local transformers inference unavailable")

# -- Capability: data ------------------------------------------------------

try:
    from ergon_builtins.registry_data import (
        BENCHMARKS as _data_benchmarks,
    )
    from ergon_builtins.registry_data import (
        EVALUATORS as _data_evaluators,
    )
    from ergon_builtins.registry_data import (
        SANDBOX_MANAGERS as _data_sandbox_managers,
    )
    from ergon_builtins.registry_data import (
        WORKERS as _data_workers,
    )

    BENCHMARKS.update(_data_benchmarks)
    EVALUATORS.update(_data_evaluators)
    SANDBOX_MANAGERS.update(_data_sandbox_managers)
    WORKERS.update(_data_workers)
except ImportError:
    log.info(
        "ergon-builtins[data] not installed; gdpeval and researchrubrics benchmarks unavailable"
    )

MODEL_BACKENDS: dict[str, Callable[..., ResolvedModel]] = dict(_model_backends)

# -- Install hints for slugs that require optional capabilities -------------

INSTALL_HINTS: dict[str, str] = {
    "transformers": "pip install 'ergon-builtins[local-models]'",
    "gdpeval": "pip install 'ergon-builtins[data]'",
    "researchrubrics": "pip install 'ergon-builtins[data]'",
    "research-rubric": "pip install 'ergon-builtins[data]'",
}
