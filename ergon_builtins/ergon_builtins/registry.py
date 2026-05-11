"""Compatibility entry point for built-in component metadata."""

import structlog

from ergon_builtins.registry_core import (
    SANDBOX_TEMPLATES,
)
from ergon_builtins.registry_core import register_core_builtins

log = structlog.get_logger()

# -- Explicit registration --------------------------------------------------


def register_builtins(_target: object | None = None) -> None:
    """Register builtins available in the current environment."""

    register_core_builtins()
    _register_local_model_builtins()
    _register_data_builtins()


def _register_local_model_builtins() -> None:
    try:
        from ergon_builtins.registry_local_models import register_local_model_builtins
    except ImportError:
        log.info(
            "ergon-builtins[local-models] not installed; local transformers inference unavailable"
        )
        return

    register_local_model_builtins()


def _register_data_builtins() -> None:
    try:
        from ergon_builtins.registry_data import register_data_builtins
    except ImportError:
        log.info(
            "ergon-builtins[data] not installed; gdpeval and researchrubrics benchmarks unavailable"
        )
        return

    register_data_builtins()


# -- Install hints for slugs that require optional capabilities -------------

INSTALL_HINTS: dict[str, str] = {
    "transformers": "pip install 'ergon-builtins[local-models]'",
    "gdpeval": "pip install 'ergon-builtins[data]'",
    "researchrubrics": "pip install 'ergon-builtins[data]'",
    "research-rubric": "pip install 'ergon-builtins[data]'",
}
