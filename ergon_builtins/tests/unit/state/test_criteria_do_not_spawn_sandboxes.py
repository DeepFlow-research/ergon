"""State test: no criterion file directly instantiates a BaseSandboxManager subclass.

Criteria MUST route all sandbox access through the ``CriterionRuntime`` DI surface
(``context.runtime.ensure_sandbox()`` etc.).  This test AST-scans every
``criterion.py`` under ``ergon_builtins/`` and fails if any file contains a
pattern that constructs a sandbox manager directly.

Closes: docs/bugs/open/2026-04-18-swebench-criterion-spawns-sandbox.md
Refs: docs/rfcs/active/2026-04-17-criterion-runtime-di-container.md
"""

from __future__ import annotations

import re
from pathlib import Path

# Adjust this root to be repo-relative if needed; uses __file__ for portability.
_REPO_ROOT = Path(__file__).parent.parent.parent
CRITERION_DIR = _REPO_ROOT / "ergon_builtins" / "ergon_builtins" / "benchmarks"

# Pattern that matches direct sandbox manager instantiation: e.g. SomeSandboxManager()
# or SomeSandboxManager(  (multi-line construction).
SANDBOX_MANAGER_PATTERN = re.compile(r"\bSandboxManager\s*\(")


def test_criteria_do_not_instantiate_sandbox_managers() -> None:
    """No criterion.py under ergon_builtins/benchmarks/ may construct a SandboxManager."""
    offenders: list[str] = []
    for path in sorted(CRITERION_DIR.rglob("criterion.py")):
        content = path.read_text()
        if SANDBOX_MANAGER_PATTERN.search(content):
            offenders.append(str(path.relative_to(_REPO_ROOT)))
    assert not offenders, (
        "Criterion files directly instantiate a SandboxManager — "
        "use context.runtime.ensure_sandbox() instead:\n" + "\n".join(f"  {p}" for p in offenders)
    )
