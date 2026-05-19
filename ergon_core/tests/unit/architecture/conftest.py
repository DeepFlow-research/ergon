"""Pytest hooks for the architecture-guard test suite.

Hosts the `pytest_collection_modifyitems` hook that applies xfail
markers from per-file `_KNOWN_VIOLATORS` dicts. Defined in conftest.py
(not in the test files themselves) so pytest reliably picks it up at
collection time.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pytest


def _violators_for(item: Any) -> Mapping[tuple[str, str], str] | None:
    """Return the `_KNOWN_VIOLATORS` dict for `item`'s test module, if
    the module defines one."""

    module = item.module
    return getattr(module, "_KNOWN_VIOLATORS", None)


def pytest_collection_modifyitems(config, items):
    # `config` is part of pytest's hook contract; intentionally unused.
    del config
    for item in items:
        if "[" not in item.name:
            continue
        violators = _violators_for(item)
        if not violators:
            continue
        test_name, _, param = item.name.partition("[")
        param = param.rstrip("]")
        reason = violators.get((test_name, param))
        if reason is not None:
            item.add_marker(pytest.mark.xfail(reason=reason, strict=True))
