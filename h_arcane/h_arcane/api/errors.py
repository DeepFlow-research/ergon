"""Public API error types."""


class DependencyError(Exception):
    """A component's required package is not installed."""
