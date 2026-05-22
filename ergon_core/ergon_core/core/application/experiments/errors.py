"""Errors raised by the experiments domain.

Typed exceptions so callers can `except DefinitionNotFoundError:`
specifically rather than catching generic `ValueError` and string-
matching the message. See 07-test-strategy.md § Repository layer
standard rule 8.
"""

from uuid import UUID


class ExperimentDomainError(Exception):
    """Base for all experiments-domain errors."""


class DefinitionNotFoundError(ExperimentDomainError):
    """Lookup failed for an `ExperimentDefinition` row."""

    def __init__(self, definition_id: UUID) -> None:
        super().__init__(f"ExperimentDefinition {definition_id} not found")
        self.definition_id = definition_id


class DefinitionTaskNotFoundError(ExperimentDomainError):
    """Lookup failed for an `ExperimentDefinitionTask` row."""

    def __init__(self, task_id: UUID) -> None:
        super().__init__(f"ExperimentDefinitionTask {task_id} not found")
        self.task_id = task_id


class DefinitionInstanceNotFoundError(ExperimentDomainError):
    """Lookup failed for an `ExperimentDefinitionInstance` row."""

    def __init__(self, instance_id: UUID) -> None:
        super().__init__(f"ExperimentDefinitionInstance {instance_id} not found")
        self.instance_id = instance_id
