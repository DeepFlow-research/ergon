"""Tests for ResearchRubrics benchmark registration and vanilla variant."""

import pytest


class TestResearchRubricsBenchmarkRegistration:
    """Verify benchmark slugs resolve correctly in the registry."""

    def test_researchrubrics_ablated_registered(self):
        """researchrubrics-ablated resolves to ResearchRubricsBenchmark."""
        from ergon_builtins.registry_data import BENCHMARKS

        assert "researchrubrics-ablated" in BENCHMARKS
        cls = BENCHMARKS["researchrubrics-ablated"]
        assert cls.__name__ == "ResearchRubricsBenchmark"

    def test_researchrubrics_vanilla_registered(self):
        """researchrubrics-vanilla resolves to ResearchRubricsVanillaBenchmark."""
        from ergon_builtins.registry_data import BENCHMARKS

        assert "researchrubrics-vanilla" in BENCHMARKS
        cls = BENCHMARKS["researchrubrics-vanilla"]
        assert cls.__name__ == "ResearchRubricsVanillaBenchmark"

    def test_worker_slugs_registered(self):
        """researchrubrics-researcher is present in the registry."""
        from ergon_builtins.registry_data import WORKERS

        assert "researchrubrics-researcher" in WORKERS


class TestResearchRubricsVanillaBenchmark:
    """Verify the vanilla benchmark subclass."""

    def test_vanilla_type_slug(self):
        from ergon_builtins.benchmarks.researchrubrics.vanilla import (
            ResearchRubricsVanillaBenchmark,
        )

        assert ResearchRubricsVanillaBenchmark.type_slug == "researchrubrics-vanilla"

    def test_vanilla_uses_scaleai_dataset(self):
        from ergon_builtins.benchmarks.researchrubrics.vanilla import (
            ResearchRubricsVanillaBenchmark,
        )

        # Construction should set dataset_name to ScaleAI's
        benchmark = ResearchRubricsVanillaBenchmark(limit=1)
        assert benchmark.dataset_name == "ScaleAI/researchrubrics"
        assert benchmark.name == "researchrubrics-vanilla"
