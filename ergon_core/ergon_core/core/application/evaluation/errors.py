"""Evaluation-domain errors."""


class EvaluationError(Exception):
    """Base for evaluation-domain failures."""

class ResourceNotFoundError(LookupError):
    """Raised by ``read_resource`` when no ``RunResource`` row matches the name."""

