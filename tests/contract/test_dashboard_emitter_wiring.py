"""Contract test: every DashboardEmitter public method must have at least one
call site in ergon_core/, ergon_builtins/, or ergon_infra/.

Fails CI when an emitter method is added without a corresponding call site.
See docs/rfcs/active/2026-04-18-dashboard-event-wiring-enforcement.md.
"""

from __future__ import annotations

import inspect
import re
from pathlib import Path
from typing import Final

import pytest

from ergon_core.core.dashboard.emitter import DashboardEmitter

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Paths to scan (relative to the repo root, which is determined at runtime).
_SCAN_PACKAGES: Final[tuple[str, ...]] = (
    "ergon_core",
    "ergon_builtins",
    "ergon_infra",
)

# Files that DEFINE the emitter — excluded from the scan so self-references
# inside emitter.py don't count as call sites.
_DEFINITION_FILES: Final[frozenset[str]] = frozenset(
    {
        "ergon_core/ergon_core/core/dashboard/emitter.py",
        "ergon_core/ergon_core/core/dashboard/event_contracts.py",
        "ergon_core/ergon_core/core/providers/sandbox/event_sink.py",
    }
)

# Methods exempt from the zero-call-sites check.
# register_execution: internal mapping helper, not a dashboard event.
# Sandbox trio: DashboardEmitterSandboxEventSink (event_sink.py) is their
#   proof-of-wiring; the sink-activation gap is a separate bug.
_EXEMPT_METHODS: Final[frozenset[str]] = frozenset(
    {
        "register_execution",
        "sandbox_created",
        "sandbox_command",
        "sandbox_closed",
    }
)


def _repo_root() -> Path:
    """Find the repo root by walking up from this file until pyproject.toml
    is found, or fall back to the tests/ grandparent."""
    p = Path(__file__).resolve()
    for parent in p.parents:
        if (parent / "pyproject.toml").exists():
            return parent
    return p.parent.parent.parent


def _emitter_method_names() -> list[str]:
    """Return public async method names on DashboardEmitter."""
    return [
        name
        for name, member in inspect.getmembers(DashboardEmitter, predicate=inspect.isfunction)
        if not name.startswith("_") and inspect.iscoroutinefunction(member)
    ]


def _call_patterns(method_name: str) -> list[str]:
    """Return the grep patterns that count as proof-of-wiring for a method.

    Accepts:
      - Direct call:      .method_name(
      - Listener wiring:  add_listener(...emitter.method_name  (no open paren needed)
      - Listener wiring:  add_mutation_listener(...emitter.method_name
    """
    return [
        rf"\.{re.escape(method_name)}\(",
        rf"add_listener\(.*\.{re.escape(method_name)}\b",
        rf"add_mutation_listener\(.*\.{re.escape(method_name)}\b",
    ]


def _has_call_site(method_name: str, repo_root: Path) -> bool:
    """Return True if at least one non-definition file contains a call site."""
    for package in _SCAN_PACKAGES:
        package_path = repo_root / package
        if not package_path.exists():
            continue
        for py_file in package_path.rglob("*.py"):
            rel = str(py_file.relative_to(repo_root))
            if rel in _DEFINITION_FILES:
                continue
            try:
                source = py_file.read_text(encoding="utf-8")
            except OSError:
                continue
            for pattern in _call_patterns(method_name):
                if re.search(pattern, source):
                    return True
    return False


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestDashboardEmitterWiring:
    """Every public DashboardEmitter method must have at least one call site."""

    @pytest.mark.xfail(
        reason=(
            "9 of 12 DashboardEmitter methods have zero call sites — tracked in "
            "docs/bugs/open/2026-04-18-dashboard-emitter-methods-not-wired.md. "
            "Remove this xfail marker once the bug-fix PR (Implementation Order "
            "Step 1 in docs/rfcs/active/2026-04-18-dashboard-event-wiring-enforcement.md) "
            "lands."
        ),
        strict=True,
    )
    def test_no_unwired_methods(self) -> None:
        """Enumerate all public async methods; fail if any have zero call sites.

        The full list of unwired methods is reported in a single failure so the
        developer sees all gaps at once rather than fixing one at a time.

        Currently xfail: the bug-fix PR (Step 1) has not landed yet.  Once
        call sites are added for the 9 unwired methods, remove the xfail marker
        and this test becomes the CI gate.
        """
        repo_root = _repo_root()
        methods = _emitter_method_names()

        unwired: list[str] = []
        for method_name in methods:
            if method_name in _EXEMPT_METHODS:
                continue
            if not _has_call_site(method_name, repo_root):
                unwired.append(method_name)

        if unwired:
            pytest.fail(
                "DashboardEmitter methods with zero call sites in "
                "ergon_core/, ergon_builtins/, ergon_infra/:\n"
                + "\n".join(f"  - {m}" for m in sorted(unwired))
                + "\n\nFor each method, add a call site at the point of the "
                "corresponding state mutation.  See:\n"
                "  docs/bugs/open/2026-04-18-dashboard-emitter-methods-not-wired.md\n"
                "  docs/rfcs/active/2026-04-18-dashboard-event-wiring-enforcement.md",
            )

    @pytest.mark.parametrize("method_name", _emitter_method_names())
    def test_method_is_async(self, method_name: str) -> None:
        """Guard against accidentally making an emitter method sync.

        All DashboardEmitter public methods must be async — they call
        inngest_client.send(), which is a coroutine.
        """
        member = getattr(DashboardEmitter, method_name)
        assert inspect.iscoroutinefunction(member), (
            f"DashboardEmitter.{method_name} is not async. "
            "All emitter methods must be async coroutines."
        )

    def test_exempt_methods_still_exist(self) -> None:
        """The exempt list must not drift from the actual class definition.

        If an exempt method is renamed or removed, this test catches it so the
        skip list is kept honest.
        """
        all_methods = set(_emitter_method_names())
        # Exempt methods that are NOT async (register_execution) are excluded
        # from the async method list; check all members including sync ones.
        all_public = {
            name
            for name, _ in inspect.getmembers(DashboardEmitter, predicate=inspect.isfunction)
            if not name.startswith("_")
        }
        missing_from_class = _EXEMPT_METHODS - all_public
        assert not missing_from_class, (
            f"Exempt methods not found on DashboardEmitter: {missing_from_class}. "
            "Update _EXEMPT_METHODS in this file."
        )
