"""Shared benchmark types."""

from enum import Enum


class BenchmarkName(str, Enum):
    """Supported benchmark names."""

    GDPEVAL = "gdpeval"
    MINIF2F = "minif2f"
    RESEARCHRUBRICS = "researchrubrics"
    CUSTOM = "custom"  # For user-defined workflows
    SMOKE_TEST = "smoke_test"  # Lightweight benchmark for pipeline validation
