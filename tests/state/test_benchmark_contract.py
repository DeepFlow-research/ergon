"""Contract: every registered benchmark declares onboarding_deps and template_spec."""

from __future__ import annotations

import pytest

from ergon_core.api.benchmark_deps import BenchmarkDeps
from ergon_core.api.template_spec import TemplateSpec, _NoSetupType


class TestBenchmarkOnboardingDepsContract:
    """Every benchmark in both registries must declare onboarding_deps."""

    def test_core_benchmarks_have_onboarding_deps(self) -> None:
        from ergon_builtins.registry_core import BENCHMARKS

        for slug, cls in BENCHMARKS.items():
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
        from ergon_builtins.registry_core import BENCHMARKS

        for slug, cls in BENCHMARKS.items():
            deps = cls.onboarding_deps
            with pytest.raises(Exception):  # Pydantic ValidationError
                deps.e2b = not deps.e2b  # type: ignore[misc]

    def test_known_e2b_benchmarks(self) -> None:
        from ergon_builtins.registry_core import BENCHMARKS

        assert BENCHMARKS["smoke-test"].onboarding_deps.e2b is True
        assert BENCHMARKS["minif2f"].onboarding_deps.e2b is True
        assert BENCHMARKS["swebench-verified"].onboarding_deps.e2b is True
        assert BENCHMARKS["delegation-smoke"].onboarding_deps.e2b is False
        assert BENCHMARKS["researchrubrics-smoke"].onboarding_deps.e2b is False


class TestBenchmarkTemplateSpecContract:
    """Every benchmark in both registries must declare template_spec."""

    def test_core_benchmarks_have_template_spec(self) -> None:
        from ergon_builtins.registry_core import BENCHMARKS

        for slug, cls in BENCHMARKS.items():
            assert hasattr(cls, "template_spec"), (
                f"Benchmark '{slug}' ({cls.__qualname__}) is missing 'template_spec'. "
                f"Add 'template_spec: ClassVar[TemplateSpec | NoSetupSentinel] = NoSetup' "
                f"(or a TemplateSpec) to the class body."
            )
            spec = cls.template_spec
            assert isinstance(spec, (TemplateSpec, _NoSetupType)), (
                f"Benchmark '{slug}' ({cls.__qualname__}).template_spec is neither "
                f"TemplateSpec nor NoSetup. Got: {spec!r}"
            )

    def test_data_benchmarks_have_template_spec(self) -> None:
        pytest.importorskip("datasets", reason="ergon-builtins[data] not installed")
        from ergon_builtins.registry_data import BENCHMARKS

        for slug, cls in BENCHMARKS.items():
            assert hasattr(cls, "template_spec"), (
                f"Benchmark '{slug}' ({cls.__qualname__}) is missing 'template_spec'."
            )
            spec = cls.template_spec
            assert isinstance(spec, (TemplateSpec, _NoSetupType)), (
                f"Benchmark '{slug}' ({cls.__qualname__}).template_spec is neither "
                f"TemplateSpec nor NoSetup. Got: {spec!r}"
            )

    def test_template_spec_is_frozen(self) -> None:
        """TemplateSpec instances must be immutable (frozen=True)."""
        from ergon_builtins.registry_core import BENCHMARKS

        for slug, cls in BENCHMARKS.items():
            spec = cls.template_spec
            if isinstance(spec, TemplateSpec):
                with pytest.raises(Exception):  # Pydantic ValidationError
                    spec.e2b_template_id = "mutated"  # type: ignore[misc]

    def test_known_nosetup_benchmarks(self) -> None:
        from ergon_builtins.registry_core import BENCHMARKS

        assert isinstance(BENCHMARKS["smoke-test"].template_spec, _NoSetupType)
        assert isinstance(BENCHMARKS["delegation-smoke"].template_spec, _NoSetupType)
        assert isinstance(BENCHMARKS["researchrubrics-smoke"].template_spec, _NoSetupType)

    def test_known_template_spec_benchmarks(self) -> None:
        from ergon_builtins.registry_core import BENCHMARKS

        minif2f_spec = BENCHMARKS["minif2f"].template_spec
        assert isinstance(minif2f_spec, TemplateSpec)
        assert minif2f_spec.e2b_template_id == "ergon-minif2f-v1"
        assert minif2f_spec.build_recipe_path is not None

        swe_spec = BENCHMARKS["swebench-verified"].template_spec
        assert isinstance(swe_spec, TemplateSpec)
        assert swe_spec.e2b_template_id == "ergon-swebench-v1"
        assert swe_spec.build_recipe_path is not None

    def test_gdpeval_runtime_install(self) -> None:
        pytest.importorskip("pandas", reason="ergon-builtins[data] not installed")
        from ergon_builtins.registry_data import BENCHMARKS

        gdp_spec = BENCHMARKS["gdpeval"].template_spec
        assert isinstance(gdp_spec, TemplateSpec)
        assert "pdfplumber" in gdp_spec.runtime_install
        assert gdp_spec.build_recipe_path is None
        assert gdp_spec.e2b_template_id is None


class TestBenchmarkSubclassEnforcement:
    def test_missing_onboarding_deps_raises_at_class_definition(self) -> None:
        from ergon_core.api.benchmark import Benchmark

        with pytest.raises(TypeError, match="onboarding_deps"):

            class BadBenchmark(Benchmark):
                type_slug = "bad-test"

                def build_instances(self):  # type: ignore[override]
                    return {}

    def test_missing_template_spec_raises_at_class_definition(self) -> None:
        from ergon_core.api.benchmark import Benchmark
        from ergon_core.api.benchmark_deps import BenchmarkDeps

        with pytest.raises(TypeError, match="template_spec"):

            class BadBenchmarkNoSpec(Benchmark):
                type_slug = "bad-no-spec"
                onboarding_deps = BenchmarkDeps()

                def build_instances(self):  # type: ignore[override]
                    return {}

    def test_valid_declaration_does_not_raise(self) -> None:
        from ergon_core.api.benchmark import Benchmark
        from ergon_core.api.benchmark_deps import BenchmarkDeps
        from ergon_core.api.template_spec import NoSetup

        class GoodBenchmark(Benchmark):
            type_slug = "good-test"
            onboarding_deps = BenchmarkDeps()
            template_spec = NoSetup

            def build_instances(self):  # type: ignore[override]
                return {}

        # No exception raised

    def test_valid_template_spec_declaration_does_not_raise(self) -> None:
        from ergon_core.api.benchmark import Benchmark
        from ergon_core.api.benchmark_deps import BenchmarkDeps
        from ergon_core.api.template_spec import TemplateSpec

        class GoodBenchmarkWithSpec(Benchmark):
            type_slug = "good-spec-test"
            onboarding_deps = BenchmarkDeps()
            template_spec = TemplateSpec(e2b_template_id="ergon-test-v1")

            def build_instances(self):  # type: ignore[override]
                return {}

        # No exception raised
