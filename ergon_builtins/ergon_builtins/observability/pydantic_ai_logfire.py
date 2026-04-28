"""Opt-in Logfire instrumentation for pydantic-ai based built-in workers."""

import importlib
import logging
import os
from typing import Protocol, cast

logger = logging.getLogger(__name__)

_CONFIGURED = False


class LogfireModule(Protocol):
    def configure(self, **kwargs: str | bool) -> None: ...

    def instrument_pydantic_ai(self, *, include_content: bool) -> None: ...


def configure_pydantic_ai_logfire(
    *,
    logfire_module: LogfireModule | None = None,
) -> bool:
    """Configure Logfire's pydantic-ai instrumentation once when explicitly enabled."""
    global _CONFIGURED
    if os.environ.get("ERGON_LOGFIRE_PYDANTIC_AI") != "1":
        return False
    if _CONFIGURED:
        return True

    if logfire_module is None:
        logfire_module = cast(LogfireModule, importlib.import_module("logfire"))

    kwargs: dict[str, str | bool] = {
        "send_to_logfire": "if-token-present",
        "service_name": os.environ.get("ERGON_LOGFIRE_SERVICE_NAME", "ergon-builtins"),
        "environment": os.environ.get("ERGON_LOGFIRE_ENVIRONMENT", "local"),
        "console": False,
    }
    config_dir = os.environ.get("ERGON_LOGFIRE_CONFIG_DIR")
    if config_dir is not None:
        kwargs["config_dir"] = config_dir

    logfire_module.configure(**kwargs)
    logfire_module.instrument_pydantic_ai(include_content=True)
    _CONFIGURED = True
    logger.info("Enabled Logfire pydantic-ai instrumentation")
    return True


def _reset_for_tests() -> None:
    global _CONFIGURED
    _CONFIGURED = False
