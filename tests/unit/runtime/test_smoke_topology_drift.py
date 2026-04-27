"""Guard the Python smoke topology against the Playwright mirror."""

from __future__ import annotations

import ast
from pathlib import Path
import re

from ergon_core.test_support.smoke_fixtures.smoke_base.constants import (
    EXPECTED_SUBTASK_SLUGS,
)
from ergon_core.test_support.smoke_fixtures.smoke_base.recursive import NESTED_LINE_SLUGS


def test_playwright_expected_subtask_slugs_match_python_smoke_topology() -> None:
    expected_ts = Path("ergon-dashboard/tests/e2e/_shared/expected.ts")
    source = expected_ts.read_text()
    match = re.search(
        r"EXPECTED_SUBTASK_SLUGS\s*=\s*(\[[\s\S]*?\])\s+as const",
        source,
    )
    assert match is not None, "could not parse EXPECTED_SUBTASK_SLUGS from Playwright mirror"

    ts_slugs = tuple(ast.literal_eval(match.group(1)))

    assert ts_slugs == EXPECTED_SUBTASK_SLUGS


def test_playwright_expected_nested_subtask_slugs_match_python_smoke_topology() -> None:
    expected_ts = Path("ergon-dashboard/tests/e2e/_shared/expected.ts")
    source = expected_ts.read_text()
    match = re.search(
        r"EXPECTED_NESTED_SUBTASK_SLUGS\s*=\s*(\[[\s\S]*?\])\s+as const",
        source,
    )
    assert match is not None, "could not parse EXPECTED_NESTED_SUBTASK_SLUGS from Playwright mirror"

    ts_slugs = tuple(ast.literal_eval(match.group(1)))

    assert ts_slugs == NESTED_LINE_SLUGS
