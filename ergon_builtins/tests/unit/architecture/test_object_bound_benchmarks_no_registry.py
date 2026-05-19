"""After PR 10a/10b/10c land, no migrated benchmark module should
import ``ComponentRegistry`` — object-bound benchmarks construct Tasks
directly and don't go through registry resolution."""

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[4]

_MIGRATED_BENCHMARKS = (
    "minif2f",
    "swebench_verified",
    "researchrubrics",
    "gdpeval",
)

SOURCE_ROOT = ROOT / "ergon_builtins" / "ergon_builtins"


@pytest.mark.parametrize("slug", _MIGRATED_BENCHMARKS)
def test_object_bound_benchmark_does_not_import_component_registry(
    slug: str,
) -> None:
    pkg = ROOT / "ergon_builtins" / "ergon_builtins" / "benchmarks" / slug
    offenders: list[str] = []
    for path in pkg.rglob("*.py"):
        text = path.read_text()
        if "ComponentRegistry" in text:
            offenders.append(str(path.relative_to(ROOT)))
    assert offenders == [], (
        f"{slug} still depends on ComponentRegistry; PR 10 was supposed "
        f"to remove that dependency. Offenders: {offenders}"
    )


def test_toolkit_is_public_from_canonical_workers_path() -> None:
    init_file = ROOT / "ergon_builtins" / "ergon_builtins" / "workers" / "__init__.py"
    text = init_file.read_text()

    assert "from ergon_builtins.workers.toolkit import Toolkit" in text
    assert '"Toolkit"' in text


def test_workers_baselines_compat_package_is_removed() -> None:
    assert not (ROOT / "ergon_builtins" / "ergon_builtins" / "workers" / "baselines").exists()


def test_shared_workers_compat_package_is_removed() -> None:
    assert not (ROOT / "ergon_builtins" / "ergon_builtins" / "shared" / "workers").exists()


def test_worker_imports_use_canonical_paths() -> None:
    forbidden = (
        "ergon_builtins.workers.baselines",
        "ergon_builtins.shared.workers",
    )
    offenders: list[str] = []
    for path in SOURCE_ROOT.rglob("*.py"):
        text = path.read_text()
        if any(import_path in text for import_path in forbidden):
            offenders.append(str(path.relative_to(ROOT)))

    assert offenders == []


def test_builtins_do_not_import_private_manager_backed_sandbox_runtime() -> None:
    forbidden = (
        "ergon_builtins.sandbox._manager_backed",
        "BaseSandboxManager",
    )
    offenders: list[str] = []
    for path in SOURCE_ROOT.rglob("*.py"):
        text = path.read_text()
        if any(import_path in text for import_path in forbidden):
            offenders.append(str(path.relative_to(ROOT)))

    assert offenders == []


@pytest.mark.parametrize("slug", _MIGRATED_BENCHMARKS)
def test_benchmark_worker_factories_use_canonical_module(slug: str) -> None:
    benchmark_pkg = SOURCE_ROOT / "benchmarks" / slug

    assert (benchmark_pkg / "worker_factory.py").exists()
    assert not (benchmark_pkg / "workers.py").exists()


@pytest.mark.parametrize("slug", _MIGRATED_BENCHMARKS)
def test_e2b_benchmark_sandboxes_use_shared_lifecycle_base(slug: str) -> None:
    sandbox_file = SOURCE_ROOT / "benchmarks" / slug / "sandbox.py"
    text = sandbox_file.read_text()

    assert "E2BSandbox" in text
    assert "async def provision" not in text
    assert "async def _bind_runtime" not in text
