from __future__ import annotations


def test_builtin_environment_classes_are_not_exported() -> None:
    import ergon_builtins.environments as environments

    exported = set(dir(environments))

    assert "MiniF2FEnvironment" not in exported
    assert "SweBenchVerifiedEnvironment" not in exported
    assert "ResearchRubricsEnvironment" not in exported
    assert "GDPEvalEnvironment" not in exported


def test_legacy_benchmark_composition_is_not_exported_from_catalog() -> None:
    from ergon_builtins.environments import catalog

    exported = set(dir(catalog))

    assert "MiniF2FBenchmark" not in exported
    assert "SweBenchVerifiedBenchmark" not in exported
    assert "ResearchRubricsBenchmark" not in exported
    assert "GDPEvalBenchmark" not in exported
