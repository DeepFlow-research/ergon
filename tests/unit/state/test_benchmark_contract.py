"""Contract: every registered benchmark declares onboarding_deps."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from ergon_builtins.registry_core import BENCHMARKS as CORE_BENCHMARKS
from ergon_core.api.benchmark import Benchmark
from ergon_core.api.benchmark_deps import BenchmarkDeps


class TestBenchmarkOnboardingDepsContract:
    """Every benchmark in both registries must declare onboarding_deps."""

    def test_core_benchmarks_have_onboarding_deps(self) -> None:
        for slug, cls in CORE_BENCHMARKS.items():
            assert hasattr(cls, "onboarding_deps"), (
                f"Benchmark '{slug}' ({cls.__qualname__}) is missing 'onboarding_deps'. "
                f"Add 'onboarding_deps: ClassVar[BenchmarkDeps] = BenchmarkDeps(...)' "
                f"to the class body."
            )
            assert isinstance(cls.onboarding_deps, BenchmarkDeps), (
                f"Benchmark '{slug}' ({cls.__qualname__}).onboarding_deps is not a "
                f"BenchmarkDeps instance; got {type(cls.onboarding_deps)!r}."
            )

    def test_data_benchmarks_have_onboarding_deps(self) -> None:
        pytest.importorskip("datasets", reason="ergon-builtins[data] not installed")
        from ergon_builtins.registry_data import BENCHMARKS

        for slug, cls in BENCHMARKS.items():
            assert hasattr(cls, "onboarding_deps"), (
                f"Benchmark '{slug}' ({cls.__qualname__}) is missing 'onboarding_deps'."
            )
            assert isinstance(cls.onboarding_deps, BenchmarkDeps)

    def test_onboarding_deps_is_frozen(self) -> None:
        """BenchmarkDeps instances must be immutable (frozen=True via attribute access)."""
        for slug, cls in CORE_BENCHMARKS.items():
            deps = cls.onboarding_deps
            with pytest.raises(ValidationError):
                deps.e2b = not deps.e2b  # type: ignore[misc]

    def test_known_e2b_benchmarks(self) -> None:
        # ``smoke-test`` and ``researchrubrics-smoke`` benchmarks retired
        # alongside the canonical-smoke refactor.
        assert CORE_BENCHMARKS["minif2f"].onboarding_deps.e2b is True
        assert CORE_BENCHMARKS["swebench-verified"].onboarding_deps.e2b is True


class TestBenchmarkSubclassEnforcement:
    def test_missing_onboarding_deps_raises_at_class_definition(self) -> None:
        with pytest.raises(TypeError, match="onboarding_deps"):

            class BadBenchmark(Benchmark):
                type_slug = "bad-test"

                def build_instances(self):  # type: ignore[override]
                    return {}

    def test_valid_declaration_does_not_raise(self) -> None:
        class GoodBenchmark(Benchmark):
            type_slug = "good-test"
            onboarding_deps = BenchmarkDeps()

            def build_instances(self):  # type: ignore[override]
                return {}

        # No exception raised
