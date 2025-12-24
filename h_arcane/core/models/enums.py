"""Shared benchmark types."""

from enum import Enum


class BenchmarkName(str, Enum):
    """Supported benchmark names."""

    GDPEVAL = "gdpeval"
    MINIF2F = "minif2f"
    RESEARCHRUBRICS = "researchrubrics"
