"""Opt-in Logfire instrumentation for pydantic-ai based built-in workers."""

from __future__ import annotations

import importlib
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

_CONFIGURED = False


def configure_pydantic_ai_logfire(*, logfire_module: Any | None = None) -> bool:
    """Configure Logfire's pydantic-ai instrumentation once when explicitly enabled."""
    global _CONFIGURED
    if os.environ.get("ERGON_LOGFIRE_PYDANTIC_AI") != "1":
        return False
    if _CONFIGURED:
        return True

    if logfire_module is None:
        logfire_module = importlib.import_module("logfire")

    kwargs = {
        "send_to_logfire": "if-token-present",
        "service_name": os.environ.get("ERGON_LOGFIRE_SERVICE_NAME", "ergon-builtins"),
        "environment": os.environ.get("ERGON_LOGFIRE_ENVIRONMENT", "local"),
        "config_dir": os.environ.get("ERGON_LOGFIRE_CONFIG_DIR"),
        "console": False,
    }
    if kwargs["config_dir"] is None:
        kwargs.pop("config_dir")

    logfire_module.configure(**kwargs)
    logfire_module.instrument_pydantic_ai(include_content=True)
    _CONFIGURED = True
    logger.info("Enabled Logfire pydantic-ai instrumentation")
    return True


def _reset_for_tests() -> None:
    global _CONFIGURED
    _CONFIGURED = False
