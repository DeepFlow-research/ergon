"""Config-time descriptor for a worker binding."""

from ergon_core.api.registry import registry
from pydantic import BaseModel, ConfigDict


class WorkerSpec(BaseModel):
    """Immutable descriptor for a worker binding in an Experiment."""

    model_config = ConfigDict(frozen=True)

    worker_slug: str
    name: str
    model: str

    def validate_spec(self) -> None:
        """Check that ``worker_slug`` refers to a known registry entry."""
        if self.worker_slug not in registry.workers:
            known = ", ".join(sorted(registry.workers)) or "<none>"
            raise ValueError(
                f"Unknown worker slug {self.worker_slug!r}; registered workers: {known}"
            )
        if not self.name:
            raise ValueError("WorkerSpec.name must be a non-empty string")
        if not self.model:
            raise ValueError("WorkerSpec.model must be a non-empty string")
