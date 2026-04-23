"""Public API error types."""


class DependencyError(Exception):
    """A component's required package is not installed."""


class CriteriaCheckError(Exception):
    """A criterion rejected the run for domain reasons (shape, probes, content).

    Implementations such as :class:`~ergon_core.api.criterion.Criterion`
    subclasses may raise this from verification helpers; the criterion's
    ``evaluate`` method is expected to catch it and return
    ``CriterionResult(passed=False, …)``. Bugs and infrastructure failures
    should use other exception types so they propagate loudly.
    """
