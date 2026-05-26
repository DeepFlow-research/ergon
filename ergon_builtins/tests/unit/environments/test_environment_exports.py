from __future__ import annotations


def test_all_builtin_environment_exports_exist() -> None:
    from ergon_builtins.environments import (
        GDPEvalEnvironment,
        MiniF2FEnvironment,
        ResearchRubricsEnvironment,
        SweBenchVerifiedEnvironment,
    )

    assert MiniF2FEnvironment.__name__ == "MiniF2FEnvironment"
    assert SweBenchVerifiedEnvironment.__name__ == "SweBenchVerifiedEnvironment"
    assert ResearchRubricsEnvironment.__name__ == "ResearchRubricsEnvironment"
    assert GDPEvalEnvironment.__name__ == "GDPEvalEnvironment"


def test_legacy_benchmark_composition_is_not_exported_from_catalog() -> None:
    from ergon_builtins.benchmarks import catalog

    exported = set(dir(catalog))

    assert "MiniF2FBenchmark" not in exported
    assert "SweBenchVerifiedBenchmark" not in exported
    assert "ResearchRubricsBenchmark" not in exported
    assert "GDPEvalBenchmark" not in exported
