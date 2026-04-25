"""Tests for ResearchRubrics benchmark registration and vanilla variant."""

import pytest
from ergon_builtins.benchmarks.researchrubrics.benchmark import ResearchRubricsBenchmark
from ergon_builtins.benchmarks.researchrubrics.vanilla import ResearchRubricsVanillaBenchmark
from ergon_builtins.registry_data import BENCHMARKS, WORKERS
from ergon_core.api import Benchmark


class TestResearchRubricsBenchmarkRegistration:
    """Verify benchmark slugs resolve correctly in the registry."""

    def test_researchrubrics_ablated_registered(self):
        """researchrubrics-ablated resolves to ResearchRubricsBenchmark."""
        assert "researchrubrics-ablated" in BENCHMARKS
        assert BENCHMARKS["researchrubrics-ablated"] is ResearchRubricsBenchmark
        assert issubclass(ResearchRubricsBenchmark, Benchmark)

    def test_researchrubrics_vanilla_registered(self):
        """researchrubrics-vanilla resolves to ResearchRubricsVanillaBenchmark."""
        assert "researchrubrics-vanilla" in BENCHMARKS
        assert BENCHMARKS["researchrubrics-vanilla"] is ResearchRubricsVanillaBenchmark
        assert issubclass(ResearchRubricsVanillaBenchmark, Benchmark)

    def test_worker_slugs_registered(self):
        expected = {"researchrubrics-researcher"}
        missing = expected - set(WORKERS.keys())
        assert not missing, f"Expected worker slugs missing from registry: {missing}"


class TestResearchRubricsVanillaBenchmark:
    """Verify the vanilla benchmark subclass."""

    def test_vanilla_type_slug(self):
        assert ResearchRubricsVanillaBenchmark.type_slug == "researchrubrics-vanilla"

    def test_vanilla_uses_scaleai_dataset(self):
        # Construction should set dataset_name to ScaleAI's
        benchmark = ResearchRubricsVanillaBenchmark(limit=1)
        assert benchmark.dataset_name == "ScaleAI/researchrubrics"
        assert benchmark.name == "researchrubrics-vanilla"
