"""Dependency checking utilities for component validation."""

import importlib.util


def check_packages(
    required: list[str],
    component_label: str,
) -> list[str]:
    """Check that required packages are importable.

    Returns a list of human-readable error strings.  Empty list = all good.
    """
    errors: list[str] = []
    for spec in required:
        name = spec.split(">=")[0].split("<=")[0].split("==")[0].split("<")[0].strip()
        if importlib.util.find_spec(name) is None:
            errors.append(f"{component_label} requires '{spec}' but it is not installed")
    return errors
