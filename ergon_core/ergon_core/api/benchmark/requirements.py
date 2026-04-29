"""Onboarding dependency descriptor for Benchmark subclasses."""

from pydantic import BaseModel


class BenchmarkRequirements(BaseModel, frozen=True):
    """Onboarding requirements for a single benchmark."""

    e2b: bool = False
    extras: tuple[str, ...] = ()
    optional_keys: tuple[str, ...] = ()
