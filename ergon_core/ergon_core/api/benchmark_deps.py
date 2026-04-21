"""Onboarding dependency descriptor for Benchmark subclasses."""

from pydantic import BaseModel


class BenchmarkDeps(BaseModel, frozen=True):
    """Onboarding requirements for a single benchmark.

    Declared as a ClassVar on every Benchmark subclass. The onboarding
    wizard reads these to determine which API keys to prompt for and
    which pip extras to install.

    This is the single source of truth for a benchmark's onboarding
    requirements. Do not add a corresponding entry in any dict elsewhere.
    """

    e2b: bool = False
    extras: tuple[str, ...] = ()
    optional_keys: tuple[str, ...] = ()
